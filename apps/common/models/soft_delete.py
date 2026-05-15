# apps/common/models/soft_delete.py
"""
Soft-delete infrastructure for the Fashionistar platform.

Architecture:
    SoftDeleteModel     — Abstract mixin: marks records as deleted instead
                          of physically removing them.  Pairs with
                          ``SoftDeleteManager`` (apps/common/managers.py)
                          which filters out ``is_deleted=True`` rows from
                          normal QuerySets.
    DeletedRecords      — Archive table: stores serialised snapshots of
                          every soft-deleted instance for forensic recovery
                          and compliance audits.
    DeletionAuditCounter — Atomic cumulative counters per
                           (model_name, action) pair — tracks soft-delete,
                           hard-delete, and restore totals for every model.
    HardDeleteMixin     — Permission-gated hard-delete with Cloudinary
                          media cleanup and pre-delete notification.

Design Principles:
    - QuerySet.update() is always preferred over self.save() to avoid
      re-triggering model validation / pre_save signals.
    - Celery notifications are fire-and-forget (retry=False, 1s timeout)
      so a dead broker NEVER blocks the caller.
    - Analytics counters are dispatched via transaction.on_commit() to
      prevent phantom increments on transaction rollback.
"""

import logging

from django.core.exceptions import PermissionDenied
from django.db import models, transaction as db_transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ================================================================
# 2. SOFT-DELETE MODEL
# ================================================================

class SoftDeleteModel(models.Model):
    """Abstract base class that prevents physical deletion.

    Records are marked as deleted (``is_deleted=True``) and archived to
    ``DeletedRecords`` for forensic recovery. The default manager
    (``SoftDeleteManager``) filters out deleted records from normal
    queries — they reappear only when the admin or audit code explicitly
    calls ``all_with_deleted()``.

    On soft-delete and restore, fire-and-forget Celery tasks dispatch
    email/SMS notifications to the affected user. Tasks are dispatched
    with ``retry=False`` and a 1-second socket timeout so they NEVER
    block the caller — even when Redis / the broker is completely down.

    Usage:
        class MyModel(SoftDeleteModel, TimeStampedModel):
            name = models.CharField(max_length=255)

        instance = MyModel.objects.get(pk=pk)
        instance.soft_delete()   # marks deleted, archives snapshot
        instance.restore()       # reverses the soft-delete
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

    @classmethod
    def _all_records_queryset(cls):
        """Return an unfiltered queryset that includes deleted rows."""
        manager = getattr(cls, "objects", None)
        if manager is not None and hasattr(manager, "all_with_deleted"):
            return manager.all_with_deleted()
        return cls._base_manager.all()

    # ----------------------------------------------------------------
    # Soft-delete
    # ----------------------------------------------------------------

    def soft_delete(self):
        """Mark this record as deleted and archive a serialised snapshot.

        Steps:
            1. Serialise a snapshot into ``DeletedRecords``.
            2. ``QuerySet.update()`` — bypasses ``full_clean()``
               to avoid crashing on models with immutability guards
               (e.g. ``UnifiedUser``).
            3. Sync in-memory state so callers see the updated values
               without re-fetching from DB.
            4. Fire-and-forget Celery notification (email/SMS).
            5. Dispatch analytics counter update via ``on_commit()``.

        Raises:
            Exception: Re-raises any DB or serialisation error after
                logging it. Callers must handle ``ProtectedError`` if
                the model has ``PROTECT`` reverse relations.

        Note:
            We use ``QuerySet.update()`` throughout this class, never
            ``self.save()``, to avoid re-triggering model validation.
        """
        try:
            from apps.common.models import DeletedRecords
            from django.forms.models import model_to_dict

            with db_transaction.atomic():
                # ── 1. Archive snapshot ──────────────────────────────
                try:
                    archive_data = model_to_dict(self)
                    serialized = {
                        k: str(v) if v is not None else None
                        for k, v in archive_data.items()
                    }
                except Exception:
                    serialized = {'pk': str(self.pk)}

                now = timezone.now()
                updated = self.__class__.objects.filter(
                    pk=self.pk,
                    is_deleted=False,
                ).update(
                    is_deleted=True,
                    deleted_at=now,
                )

                if updated == 0:
                    logger.warning(
                        "soft_delete() matched 0 rows for %s %s — already deleted or missing",
                        self.__class__.__name__,
                        self.pk,
                    )
                    return

                DeletedRecords.objects.create(
                    model_name=self.__class__.__name__,
                    record_id=str(self.pk),
                    data=serialized,
                )

            if updated == 0:
                logger.warning(
                    "soft_delete() matched 0 rows for %s %s — already deleted or missing",
                    self.__class__.__name__,
                    self.pk,
                )
                return

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

            # ── 5. Update analytics counter ──────────────────────
            try:
                from apps.common.models import ModelAnalytics
                ModelAnalytics.record_soft_deleted(
                    model_name=self.__class__.__name__,
                    app_label=(
                        self.__class__._meta.app_label
                    ),
                )
            except Exception:
                pass  # Never block on analytics

        except Exception:
            logger.exception(
                "Error during soft-delete of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    async def asoft_delete(self):
        """Async variant of ``soft_delete()``.

        Identical logic but uses async ORM methods (``acreate``,
        ``aupdate``) to avoid blocking an async Django view or
        Channels consumer.
        """
        try:
            from apps.common.models import DeletedRecords
            from django.forms.models import model_to_dict

            try:
                archive_data = model_to_dict(self)
                serialized = {
                    k: str(v) if v is not None else None
                    for k, v in archive_data.items()
                }
            except Exception:
                serialized = {'pk': str(self.pk)}

            now = timezone.now()
            updated = await self.__class__.objects.filter(
                pk=self.pk,
                is_deleted=False,
            ).aupdate(
                is_deleted=True,
                deleted_at=now,
            )

            if updated == 0:
                logger.warning(
                    "asoft_delete() matched 0 rows for %s %s — already deleted or missing",
                    self.__class__.__name__,
                    self.pk,
                )
                return

            await DeletedRecords.objects.acreate(
                model_name=self.__class__.__name__,
                record_id=str(self.pk),
                data=serialized,
            )

            self.is_deleted = True
            self.deleted_at = now

            logger.info(
                "Soft-deleted %s with ID %s (async)",
                self.__class__.__name__,
                self.pk,
            )

            self._fire_and_forget_notification('soft_deleted')

            try:
                from apps.common.models import ModelAnalytics
                ModelAnalytics._dispatch(
                    model_name=self.__class__.__name__,
                    app_label=self.__class__._meta.app_label,
                    total_active=-1,
                    total_soft_deleted=1
                )
            except Exception:
                pass

        except Exception:
            logger.exception(
                "Error during async soft-delete of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    # ----------------------------------------------------------------
    # Restore
    # ----------------------------------------------------------------

    def restore(self):
        """Restore a soft-deleted record to active state.

        Steps:
            1. ``QuerySet.update()`` via ``all_with_deleted()`` manager
               so the UPDATE actually finds the ``is_deleted=True`` row.
               The default alive-only manager would silently match 0 rows.
            2. Purge the matching ``DeletedRecords`` archive entry.
            3. Sync in-memory state.
            4. Fire-and-forget Celery notification.
            5. Dispatch analytics counter update.

        Note:
            BUG FIX: Previous implementation used
            ``self.__class__.objects.filter(pk=self.pk)`` which uses the
            alive-only manager and always returns an empty queryset for
            deleted records → 0 rows updated → silent no-op. We now
            explicitly call ``all_with_deleted()`` to bypass the alive
            filter.
        """
        try:
            # ── 1. Bulk UPDATE via unfiltered manager ────────────
            from apps.common.models import DeletedRecords

            with db_transaction.atomic():
                updated = self.__class__._all_records_queryset().filter(
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
                    return

                # ── 2. Purge archive entry ───────────────────────────
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

            # ── 5. Update analytics counter ──────────────────────
            try:
                from apps.common.models import ModelAnalytics
                ModelAnalytics.record_restored(
                    model_name=self.__class__.__name__,
                    app_label=(
                        self.__class__._meta.app_label
                    ),
                )
            except Exception:
                pass  # Never block on analytics

        except Exception:
            logger.exception(
                "Error during restore of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    async def arestore(self):
        """Async variant of ``restore()``.

        Identical logic but uses async ORM methods to avoid blocking
        an async Django view or Channels consumer.
        """
        try:
            updated = await self.__class__._all_records_queryset().filter(
                pk=self.pk,
                is_deleted=True,
            ).aupdate(
                is_deleted=False,
                deleted_at=None,
            )

            from apps.common.models import DeletedRecords
            if updated == 0:
                logger.warning(
                    "arestore() matched 0 rows for %s %s "
                    "— already active or not found",
                    self.__class__.__name__,
                    self.pk,
                )
                return

            purged, _ = await DeletedRecords.objects.filter(
                model_name=self.__class__.__name__,
                record_id=str(self.pk),
            ).adelete()

            if purged:
                logger.debug(
                    "Purged %d archive entries for %s %s (async)",
                    purged,
                    self.__class__.__name__,
                    self.pk,
                )

            self.is_deleted = False
            self.deleted_at = None

            logger.info(
                "Restored %s with ID %s (async)",
                self.__class__.__name__,
                self.pk,
            )

            self._fire_and_forget_notification('restored')

            try:
                from apps.common.models import ModelAnalytics
                ModelAnalytics._dispatch(
                    model_name=self.__class__.__name__,
                    app_label=self.__class__._meta.app_label,
                    total_active=1,
                    total_soft_deleted=-1
                )
            except Exception:
                pass

        except Exception:
            logger.exception(
                "Error during async restore of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    # ----------------------------------------------------------------
    # Notification dispatch (fire-and-forget — NEVER blocks caller)
    # ----------------------------------------------------------------

    def _fire_and_forget_notification(self, action: str) -> None:
        """Enqueue email/SMS notifications as Celery background tasks.

        Design:
            - Non-blocking: ``apply_async(retry=False)`` so Celery will
              NOT retry the broker connection on failure.
            - Fail-safe: any exception (broker down, import error, etc.)
              is caught and logged as WARNING — it NEVER propagates to
              the caller. Notifications are best-effort.
            - Zero-timeout socket: ``CELERY_BROKER_TRANSPORT_OPTIONS``
              must set ``socket_timeout=1`` so a dead Redis never hangs
              the process for more than 1 second.

        Args:
            action: One of ``'soft_deleted'``, ``'hard_deleted'``,
                ``'restored'``.
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
                        retry=False,
                        ignore_result=True,
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

    # Backward-compatible alias
    _dispatch_status_notification = _fire_and_forget_notification


# ================================================================
# 3. DELETED RECORDS ARCHIVE
# ================================================================

class DeletedRecords(models.Model):
    """Archive table for soft-deleted records.

    Stores a serialised snapshot of any model instance that inherits
    ``SoftDeleteModel`` at the moment of its soft deletion.  A matching
    row is automatically removed from this table when the original
    record is restored.

    Deleting a row from this admin table (superuser only) will also
    permanently DELETE the source record from its original table — use
    with extreme caution.

    Attributes:
        model_name: Django model class name of the deleted record.
        record_id: Primary key of the deleted record (UUID or int string).
        data: JSON snapshot of all field values at deletion time.
        deleted_at: Auto-stamped timestamp when the archive row was created.
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

    def __str__(self) -> str:
        return "%s [%s] deleted at %s" % (
            self.model_name,
            self.record_id,
            self.deleted_at,
        )

    def resolve_original_model(self):
        """Dynamically resolve the original Django model class from ``model_name``.

        Returns:
            type | None: The model class, or ``None`` if it cannot be
                resolved from the installed app registry.
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
    """Cumulative audit counter for soft-delete, hard-delete, and restore ops.

    One row per (model_name, action) pair. The ``total`` field is
    atomically incremented by ``DeletionAuditCounter.increment()`` so
    concurrent requests never lose counts.

    Use Cases:
        - Total users ever created vs currently active.
        - Number of accounts soft-deleted (recoverable).
        - Number of accounts permanently purged (GDPR compliance).
        - Number of restore operations (customer retention signal).
        - Per-model deletion analytics for marketing and churn analysis.

    Access Control:
        Only superusers may view this table — enforced in the admin via
        ``has_module_perms`` and ``has_view_permission`` overrides.

    Attributes:
        model_name: Django model class name (e.g. ``'UnifiedUser'``).
        action: One of ``'soft_delete'``, ``'hard_delete'``, ``'restore'``.
        total: Cumulative count. Atomically incremented — safe under load.
        last_updated: Auto-updated timestamp of the most recent increment.
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

    def __str__(self) -> str:
        return "%s — %s: %d" % (
            self.model_name,
            self.get_action_display(),
            self.total,
        )

    @classmethod
    def increment(cls, model_name: str, action: str, count: int = 1) -> None:
        """Atomically increment the counter for a (model_name, action) pair.

        Uses ``F()`` expressions + ``update_or_create`` so concurrent
        Django processes never race-condition the counter — each increment
        is a single atomic SQL UPDATE.

        Args:
            model_name: The model class name.
            action: One of ``'soft_delete'``, ``'hard_delete'``,
                ``'restore'``.
            count: Number to add (default 1).
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
# 5. HARD-DELETE MIXIN
# ================================================================

class HardDeleteMixin:
    """Permission-gated hard-delete with Cloudinary media cleanup.

    Only superusers, admins/vendors (for their own records), or record
    owners may perform a hard delete.  Handles Cloudinary media cleanup
    and dispatches a ``'hard_deleted'`` notification before physically
    removing the record.

    Usage:
        class MyModel(HardDeleteMixin, SoftDeleteModel, TimeStampedModel):
            ...

        instance.hard_delete(user=request.user)
    """

    def hard_delete(self, user) -> None:
        """Permanently delete the record from the database.

        Args:
            user: The ``UnifiedUser`` performing the deletion.

        Raises:
            PermissionDenied: If the user is not a superuser, admin,
                vendor, or the record owner.
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

            super().delete()  # type: ignore[misc]

        except PermissionDenied:
            raise
        except Exception:
            logger.exception(
                "Error during hard-delete of %s %s",
                self.__class__.__name__,
                self.pk,
            )
            raise

    def is_owner(self, user) -> bool:
        """Return True if ``user`` is the owner of this record.

        Override in subclasses for model-specific ownership logic.

        Args:
            user: The ``UnifiedUser`` to check.

        Returns:
            bool: ``False`` by default — subclasses must override.
        """
        return False


__all__ = [
    "SoftDeleteModel",
    "DeletedRecords",
    "DeletionAuditCounter",
    "HardDeleteMixin",
]
