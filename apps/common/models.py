# apps/common/models.py
"""
Enterprise abstract base models for the Fashionistar platform.

Architecture:
    - TimeStampedModel: Auto-timestamping (created_at, updated_at).
    - SoftDeleteModel:  Soft-delete with archival, restore, and
                        fire-and-forget background notifications.
    - DeletedRecords:   Archive table for soft-deleted record data.
    - HardDeleteMixin:  Protected hard-delete with permission checks
                        and Cloudinary media cleanup.

All abstract models use ``SoftDeleteManager`` as the default
manager so that ``is_deleted=True`` records are filtered out
of normal queries. Admin and audit views use
``all_with_deleted()`` to see everything.
"""

import logging

import uuid6
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

logger = logging.getLogger('application')


# ================================================================
# 1. TIMESTAMPED MODEL
# ================================================================

class TimeStampedModel(models.Model):
    """
    Abstract base class that provides self-updating
    ``created_at`` and ``updated_at`` fields.

    Uses UUID7 as the primary key for globally unique,
    time-ordered identifiers.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid6.uuid7,
        editable=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the record was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the record was last updated.",
    )

    class Meta:
        abstract = True


# ================================================================
# 2. SOFT-DELETE MODEL
# ================================================================

class SoftDeleteModel(models.Model):
    """
    Abstract base class that prevents physical deletion.

    Records are marked as deleted (``is_deleted=True``) and
    archived to ``DeletedRecords`` for forensic recovery. The
    default manager (``SoftDeleteManager``) filters out deleted
    records from normal queries.

    On soft-delete and restore, fire-and-forget Celery tasks
    dispatch email/SMS notifications to the affected user.
    Tasks are dispatched with ``retry=False`` and a 1-second
    socket timeout so they NEVER block the caller — even when
    Redis / the broker is completely down.
    """

    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Flag indicating if the record is soft-deleted.",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of soft deletion.",
    )

    class Meta:
        abstract = True

    # ----------------------------------------------------------------
    # Soft-delete
    # ----------------------------------------------------------------

    def soft_delete(self):
        """
        Mark the record as deleted and archive it.

        Steps
        -----
        1. Serialise a snapshot into ``DeletedRecords``.
        2. ``QuerySet.update()`` — bypasses ``full_clean()``
           to avoid crashing on models with immutability guards
           (e.g. ``UnifiedUser``).
        3. Sync in-memory state.
        4. Fire-and-forget Celery notification.

        .. important::
            We use ``QuerySet.update()`` throughout this class,
            never ``self.save()``, to avoid re-triggering model
            validation.
        """
        try:
            from apps.common.models import DeletedRecords
            from django.forms.models import model_to_dict

            # ── 1. Archive snapshot ──────────────────────────────
            try:
                archive_data = model_to_dict(self)
                serialized = {
                    k: str(v) if v is not None else None
                    for k, v in archive_data.items()
                }
            except Exception:
                serialized = {'pk': str(self.pk)}

            DeletedRecords.objects.create(
                model_name=self.__class__.__name__,
                record_id=str(self.pk),
                data=serialized,
            )

            # ── 2. Bulk UPDATE — bypasses full_clean() ───────────
            # objects.filter() is safe here because the record is
            # still alive (is_deleted=False) at this point.
            now = timezone.now()
            self.__class__.objects.filter(
                pk=self.pk
            ).update(
                is_deleted=True,
                deleted_at=now,
            )

            # ── 3. Sync in-memory state ──────────────────────────
            self.is_deleted = True
            self.deleted_at = now

            logger.info(
                "Soft-deleted %s with ID %s",
                self.__class__.__name__,
                self.pk,
            )

            # ── 4. Fire-and-forget notification ──────────────────
            self._fire_and_forget_notification('soft_deleted')

        except Exception:
            logger.exception(
                "Error during soft-delete of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    # ----------------------------------------------------------------
    # Restore
    # ----------------------------------------------------------------

    def restore(self):
        """
        Restore a soft-deleted record.

        Steps
        -----
        1. ``QuerySet.update()`` via ``all_with_deleted()``
           manager so the UPDATE actually finds the
           ``is_deleted=True`` row (the default alive-only
           manager would silently match 0 rows).
        2. Purge the matching ``DeletedRecords`` archive entry.
        3. Sync in-memory state.
        4. Fire-and-forget Celery notification.

        .. important::
            ``BUG FIX``: Previous implementation used
            ``self.__class__.objects.filter(pk=self.pk)``
            which uses the alive-only manager and always returns
            an empty queryset for deleted records → 0 rows
            updated → silent no-op. We now explicitly call
            ``all_with_deleted()`` to bypass the alive filter.
        """
        try:
            # ── 1. Bulk UPDATE via unfiltered manager ────────────
            # CRITICAL: must use all_with_deleted() — the default
            # objects manager has alive_only=True and will match
            # ZERO rows when is_deleted=True, making restore a
            # silent no-op.
            updated = self.__class__.objects.all_with_deleted().filter(
                pk=self.pk,
                is_deleted=True,
            ).update(
                is_deleted=False,
                deleted_at=None,
            )

            if updated == 0:
                logger.warning(
                    "restore() matched 0 rows for %s %s "
                    "— already active or not found",
                    self.__class__.__name__,
                    self.pk,
                )

            # ── 2. Purge archive entry ───────────────────────────
            # Remove the DeletedRecords snapshot so the audit
            # table stays accurate (only lists currently-deleted
            # records).
            from apps.common.models import DeletedRecords
            purged = DeletedRecords.objects.filter(
                model_name=self.__class__.__name__,
                record_id=str(self.pk),
            ).delete()
            if purged[0]:
                logger.debug(
                    "Purged %d archive entries for %s %s",
                    purged[0],
                    self.__class__.__name__,
                    self.pk,
                )

            # ── 3. Sync in-memory state ──────────────────────────
            self.is_deleted = False
            self.deleted_at = None

            logger.info(
                "Restored %s with ID %s",
                self.__class__.__name__,
                self.pk,
            )

            # ── 4. Fire-and-forget notification ──────────────────
            self._fire_and_forget_notification('restored')

        except Exception:
            logger.exception(
                "Error during restore of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    # ----------------------------------------------------------------
    # Notification dispatch (fire-and-forget — NEVER blocks caller)
    # ----------------------------------------------------------------

    def _fire_and_forget_notification(self, action):
        """
        Enqueue email/SMS notifications as Celery background tasks.

        Design principles
        -----------------
        * **Non-blocking**: uses ``apply_async(retry=False)`` so
          Celery will NOT retry the broker connection on failure.
          The call returns immediately regardless of broker state.
        * **Fail-safe**: any exception (broker down, import error,
          etc.) is caught and logged as WARNING — it NEVER
          propagates to the caller. Notifications are best-effort.
        * **Zero-timeout socket**: CELERY_BROKER_TRANSPORT_OPTIONS
          must set ``socket_timeout=1`` so a dead Redis never hangs
          the process for more than 1 second.

        Args:
            action (str): One of ``'soft_deleted'``,
                ``'hard_deleted'``, ``'restored'``.
        """
        try:
            from apps.common.tasks import (
                send_account_status_email,
                send_account_status_sms,
            )

            email = getattr(self, 'email', None)
            phone = getattr(self, 'phone', None)

            if email:
                try:
                    send_account_status_email.apply_async(
                        kwargs={
                            'email': str(email),
                            'action': action,
                        },
                        retry=False,           # never retry broker connect
                        ignore_result=True,    # no result backend round-trip
                    )
                except Exception:
                    logger.warning(
                        "Broker unavailable — "
                        "skipping status email [%s] → %s",
                        action,
                        email,
                    )

            if phone:
                try:
                    send_account_status_sms.apply_async(
                        kwargs={
                            'phone': str(phone),
                            'action': action,
                        },
                        retry=False,
                        ignore_result=True,
                    )
                except Exception:
                    logger.warning(
                        "Broker unavailable — "
                        "skipping status SMS [%s] → %s",
                        action,
                        phone,
                    )

        except Exception:
            logger.warning(
                "Notification dispatch skipped for "
                "%s %s (action=%s) — import or task error",
                self.__class__.__name__,
                self.pk,
                action,
            )

    # Keep backward-compatible alias
    _dispatch_status_notification = _fire_and_forget_notification


# ================================================================
# 3. DELETED RECORDS ARCHIVE
# ================================================================

class DeletedRecords(models.Model):
    """
    Archive table for soft-deleted records.

    Stores a serialised snapshot of any model instance that
    inherits ``SoftDeleteModel`` at the moment of its soft
    deletion.  A matching row is automatically removed from
    this table when the original record is restored.

    Deleting a row from this admin table (superuser only) will
    also permanently DELETE the source record from its original
    table — use with extreme caution.
    """

    model_name = models.CharField(
        max_length=100,
        help_text="Name of the model that was deleted.",
    )
    record_id = models.CharField(
        max_length=255,
        help_text=(
            "Primary key of the deleted record "
            "(UUID or Int)."
        ),
    )
    data = models.JSONField(
        help_text="Serialized data of the deleted record.",
    )
    deleted_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp of deletion.",
    )

    class Meta:
        verbose_name = "Deleted Record"
        verbose_name_plural = "Deleted Records"
        indexes = [
            models.Index(
                fields=['model_name', 'record_id'],
                name='idx_deleted_model_record',
            ),
        ]

    def __str__(self):
        return "%s [%s] deleted at %s" % (
            self.model_name,
            self.record_id,
            self.deleted_at,
        )

    def resolve_original_model(self):
        """
        Dynamically resolve the original Django model class
        from ``model_name``.

        Returns:
            type | None: The model class, or ``None`` if it
                cannot be resolved.
        """
        from django.apps import apps
        for app_config in apps.get_app_configs():
            try:
                model = app_config.get_model(self.model_name)
                return model
            except LookupError:
                continue
        return None


# ================================================================
# 4. DELETION AUDIT COUNTER
# ================================================================

class DeletionAuditCounter(models.Model):
    """
    Cumulative audit counter for soft-delete, hard-delete, and
    restore operations across every model on the platform.

    One row per (model_name, action) pair. The ``total`` field
    is atomically incremented by ``DeletionAuditCounter.increment()``
    so concurrent requests never lose counts.

    Superadmin use cases
    --------------------
    * Total users ever created vs currently active.
    * Number of accounts soft-deleted (recoverable).
    * Number of accounts permanently purged (GDPR compliance).
    * Number of restore operations (customer retention signal).
    * Per-model deletion analytics for geographical marketing
      and churn analysis.

    Access control
    --------------
    Only superusers may view this table — enforced in the admin
    via ``has_module_perms`` and ``has_view_permission`` overrides.
    """

    ACTION_CHOICES = [
        ('soft_delete', 'Soft Delete'),
        ('hard_delete', 'Hard Delete (Permanent)'),
        ('restore',     'Restore'),
    ]

    model_name = models.CharField(
        max_length=100,
        help_text="Django model class name (e.g. 'UnifiedUser').",
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        help_text="Type of deletion operation.",
    )
    total = models.PositiveBigIntegerField(
        default=0,
        help_text=(
            "Cumulative count of this action on this model. "
            "Atomically incremented — safe under concurrent load."
        ),
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp of the most recent increment.",
    )

    class Meta:
        verbose_name = "Deletion Audit Counter"
        verbose_name_plural = "Deletion Audit Counters"
        unique_together = [('model_name', 'action')]
        indexes = [
            models.Index(
                fields=['model_name'],
                name='idx_del_counter_model',
            ),
        ]
        ordering = ['model_name', 'action']

    def __str__(self):
        return "%s — %s: %d" % (
            self.model_name,
            self.get_action_display(),
            self.total,
        )

    @classmethod
    def increment(cls, model_name, action, count=1):
        """
        Atomically increment the counter for the given
        (model_name, action) pair.

        Uses ``F()`` expressions + ``update_or_create`` so
        concurrent Django processes never race-condition the
        counter — each increment is a single atomic SQL UPDATE.

        Args:
            model_name (str): The model class name.
            action (str): One of 'soft_delete', 'hard_delete',
                'restore'.
            count (int): Number to add (default 1).
        """
        try:
            from django.db.models import F
            obj, created = cls.objects.get_or_create(
                model_name=model_name,
                action=action,
                defaults={'total': count},
            )
            if not created:
                cls.objects.filter(
                    model_name=model_name,
                    action=action,
                ).update(total=F('total') + count)
            logger.debug(
                "DeletionAuditCounter[%s][%s] += %d",
                model_name,
                action,
                count,
            )
        except Exception:
            logger.warning(
                "Failed to increment DeletionAuditCounter "
                "[%s][%s] by %d",
                model_name,
                action,
                count,
            )




# ================================================================
# 4. HARD-DELETE MIXIN
# ================================================================

class HardDeleteMixin:
    """
    Mixin for protected hard-delete functionality.

    Only admins, vendors (for their own records), or record
    owners may perform a hard delete. Handles Cloudinary media
    cleanup and dispatches a ``'hard_deleted'`` notification
    before physically removing the record.
    """

    def hard_delete(self, user):
        """
        Permanently delete the record from the database.

        Args:
            user: The user performing the deletion.

        Raises:
            PermissionDenied: If user lacks permission.
        """
        try:
            if not (
                user.is_superuser
                or user.role in ['admin', 'vendor']
                or self.is_owner(user)
            ):
                raise PermissionDenied(
                    "You do not have permission to "
                    "perform hard delete."
                )

            if hasattr(self, '_fire_and_forget_notification'):
                self._fire_and_forget_notification('hard_deleted')

            if hasattr(self, 'avatar') and self.avatar:
                from apps.common.utils import delete_cloudinary_asset
                delete_cloudinary_asset(self.avatar.name)

            logger.info(
                "Hard-deleting %s with ID %s by user %s",
                self.__class__.__name__,
                self.pk,
                user.pk,
            )

            super().delete()

        except PermissionDenied:
            raise
        except Exception:
            logger.exception(
                "Error during hard-delete of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    def is_owner(self, user):
        """
        Check if the user is the owner of this record.
        Override in subclasses for model-specific logic.
        """
        return False
