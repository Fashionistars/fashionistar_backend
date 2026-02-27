# apps/common/signals.py
"""
Django signals for the ``apps.common`` analytics system.

Connects ``post_save`` (creation) and ``post_delete`` (hard-delete)
signals to every registered model so that ``ModelAnalytics``
counters are updated automatically in the background.

Signal flow
-----------
1. Django fires ``post_save(created=True)`` or ``post_delete()``
   on the model instance.
2. The handler calls the appropriate ``ModelAnalytics.*`` class
   method which schedules a Celery task via
   ``transaction.on_commit()``.
3. The Celery task runs in the background, performs a
   ``SELECT ... FOR UPDATE`` + atomic ``F()`` expression UPDATE.
4. The HTTP request thread is NEVER blocked by this pipeline.

Coverage
--------
* ``post_save`` — every model in INSTALLED_APPS (excluding
  Django internals, ``ModelAnalytics`` itself, and other
  analytics/audit models to avoid circular counting).
* SoftDeleteModel subclasses — soft-delete and restore are
  captured in ``SoftDeleteModel.soft_delete()`` /
  ``SoftDeleteModel.restore()`` directly (not via ``post_save``).
  Hard-delete of soft-deleted records is captured via
  ``post_delete`` (the signal fires regardless of how delete
  was called).

Exclusions
----------
Session, LogEntry, ContentType, Token, and migration models are
excluded to keep the analytics focused on business records.
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger('application')

# ── Models we deliberately skip to avoid noise / circularity ──────
_EXCLUDED_MODEL_NAMES = frozenset({
    # Django internals
    'Session', 'ContentType', 'Permission', 'LogEntry',
    # JWT / token models
    'BlacklistedToken', 'OutstandingToken',
    # Analytics models themselves (no recursive counting)
    'ModelAnalytics', 'DeletionAuditCounter',
    # Archive / audit tables
    'DeletedRecords',
    # Celery Beat
    'CrontabSchedule', 'IntervalSchedule', 'PeriodicTask',
    'SolarSchedule', 'ClockedSchedule',
})

# ── Apps we skip entirely ─────────────────────────────────────────
_EXCLUDED_APP_LABELS = frozenset({
    'admin',          # Django admin LogEntry
    'auth',           # Permission, Group (use UnifiedUser instead)
    'contenttypes',   # ContentType
    'sessions',       # Session
    'django_celery_beat',
    'auditlog',
})


def _should_track(sender):
    """
    Return True if ``sender`` is a business model worth tracking.

    Excludes Django internals, analytics models themselves, and
    token/session tables.
    """
    meta = getattr(sender, '_meta', None)
    if meta is None:
        return False
    if meta.app_label in _EXCLUDED_APP_LABELS:
        return False
    if meta.object_name in _EXCLUDED_MODEL_NAMES:
        return False
    return True


def _get_labels(sender):
    """Return (model_name, app_label) for a model class."""
    meta = sender._meta
    return meta.object_name, meta.app_label


# ================================================================
# Signal: record CREATED
# ================================================================

@receiver(post_save)
def on_model_created(sender, instance, created, **kwargs):
    """
    Fired by ``post_save`` for every save() call.

    Only acts when ``created=True`` (new row inserted) —
    updates on existing records are ignored because they do not
    change the total or active count.

    Delegates to ``ModelAnalytics.record_created()`` which
    dispatches a fire-and-forget Celery task via
    ``transaction.on_commit()``.
    """
    if not created:
        return
    if not _should_track(sender):
        return

    # Skip soft-delete flag-only saves (not a new record)
    is_deleted = getattr(instance, 'is_deleted', None)
    if is_deleted is True:
        return  # Already counted as soft-deleted elsewhere

    model_name, app_label = _get_labels(sender)

    try:
        from apps.common.models import ModelAnalytics
        ModelAnalytics.record_created(
            model_name=model_name,
            app_label=app_label,
        )
    except Exception:
        logger.warning(
            "ModelAnalytics.record_created failed for %s "
            "— analytics may be lagging",
            model_name,
        )


# ================================================================
# Signal: record HARD-DELETED (post_delete)
# ================================================================

@receiver(post_delete)
def on_model_hard_deleted(sender, instance, **kwargs):
    """
    Fired by ``post_delete`` for every hard-delete (physical
    SQL DELETE), regardless of how it was triggered.

    Determines whether the deleted row was previously soft-deleted
    (``is_deleted=True``) so the correct counter is decremented.

    Delegates to ``ModelAnalytics.record_hard_deleted()``.

    .. note::
        Soft-delete and restore are tracked inside
        ``SoftDeleteModel.soft_delete()`` / ``restore()``
        directly, not here, because those methods use
        ``QuerySet.update()`` (which does NOT fire ``post_delete``).
    """
    if not _should_track(sender):
        return

    model_name, app_label = _get_labels(sender)
    was_soft_deleted = bool(getattr(instance, 'is_deleted', False))

    try:
        from apps.common.models import ModelAnalytics
        ModelAnalytics.record_hard_deleted(
            model_name=model_name,
            app_label=app_label,
            count=1,
            was_soft_deleted=was_soft_deleted,
        )
    except Exception:
        logger.warning(
            "ModelAnalytics.record_hard_deleted failed for %s",
            model_name,
        )
