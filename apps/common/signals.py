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

logger = logging.getLogger(__name__)

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

    Only acts when ``created=True`` (new row inserted).
    Updates route to ``on_model_updated`` below.

    Guards against soft-delete-flag-only saves (the
    ``is_deleted`` field is flipped by ``QuerySet.update()``
    which does NOT fire ``post_save``, so this guard is a
    belt-and-suspenders safety net for any edge-case path).
    """
    if not created:
        return
    if not _should_track(sender):
        return

    # Skip records that arrive pre-deleted (shouldn't happen,
    # but defensive programming)
    if getattr(instance, 'is_deleted', False):
        return

    model_name, app_label = _get_labels(sender)
    try:
        from apps.common.models import ModelAnalytics
        ModelAnalytics.record_created(
            model_name=model_name,
            app_label=app_label,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "ModelAnalytics.record_created failed for %s",
            model_name,
        )


# ================================================================
# Signal: record UPDATED (every vendor / client field change)
# ================================================================

# Fields whose lone change does NOT constitute a business update
# (these are managed by the soft-delete / restore pipeline which
# has its own explicit ModelAnalytics calls).
_SOFT_DELETE_ONLY_FIELDS = frozenset({
    'is_deleted', 'deleted_at',
})


@receiver(post_save)
def on_model_updated(sender, instance, created, **kwargs):
    """
    Fired by ``post_save`` for every UPDATE (``created=False``).

    Increments ``total_updated`` for the model so superadmins
    can track write activity from vendors, clients, and staff.

    Skips
    -----
    * Creation events (handled by ``on_model_created``).
    * Models excluded by ``_should_track()``.
    * Saves that ONLY flip ``is_deleted`` / ``deleted_at``
      (those are internal soft-delete pipeline saves; the
      correct counters are updated inside
      ``SoftDeleteModel.soft_delete()`` / ``restore()``).
    """
    if created:
        return
    if not _should_track(sender):
        return

    # Detect soft-delete-only saves: Django's update_fields kwarg
    # tells us exactly which fields were written.
    update_fields = kwargs.get('update_fields')
    if update_fields is not None:
        if set(update_fields) <= _SOFT_DELETE_ONLY_FIELDS:
            return  # Internal pipeline save — skip

    model_name, app_label = _get_labels(sender)
    try:
        from apps.common.models import ModelAnalytics
        ModelAnalytics.record_updated(
            model_name=model_name,
            app_label=app_label,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "ModelAnalytics.record_updated failed for %s",
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
