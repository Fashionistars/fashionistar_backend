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

logger = logging.getLogger(__name__)


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
        """
        Async version of soft_delete.
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

            await DeletedRecords.objects.acreate(
                model_name=self.__class__.__name__,
                record_id=str(self.pk),
                data=serialized,
            )

            now = timezone.now()
            await self.__class__.objects.filter(
                pk=self.pk
            ).aupdate(
                is_deleted=True,
                deleted_at=now,
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
        """
        Async version of restore.
        """
        try:
            updated = await self.__class__.objects.all_with_deleted().filter(
                pk=self.pk,
                is_deleted=True,
            ).aupdate(
                is_deleted=False,
                deleted_at=None,
            )

            if updated == 0:
                logger.warning(
                    "arestore() matched 0 rows for %s %s "
                    "— already active or not found",
                    self.__class__.__name__,
                    self.pk,
                )

            from apps.common.models import DeletedRecords
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
# 5. MODEL ANALYTICS — Global Record Counter
# ================================================================

class ModelAnalytics(models.Model):
    """
    Global analytics table: one row per Django model.

    Tracks the complete lifecycle of every record across the
    entire platform:

    Columns
    -------
    total_created      Cumulative count of all records ever created.
                       This number ONLY goes up — soft-delete and
                       hard-delete do NOT decrement it.
    total_active       Count of currently live (is_deleted=False)
                       records.  Decrements on delete, increments
                       on restore or creation.
    total_soft_deleted Count of records currently flagged as
                       is_deleted=True (still in DB, recoverable).
    total_hard_deleted Cumulative count of records permanently
                       removed from the DB (never decrements).

    Identity equation (always true)
    --------------------------------
        total_created = total_active
                      + total_soft_deleted
                      + total_hard_deleted

    Race-condition safety
    ---------------------
    All mutations go through ``_adjust()`` which wraps a
    ``SELECT ... FOR UPDATE`` + ``F()`` expression in a single
    ``transaction.atomic()`` block.  This eliminates lost-update
    races even under 100K+ concurrent requests.

    Performance
    -----------
    Mutations are dispatched as fire-and-forget Celery tasks
    via ``transaction.on_commit()`` so the hot path of every
    model save/delete is NEVER slowed down.

    Access
    ------
    Superadmin-only read-only admin dashboard.
    """

    model_name = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Django model class name (e.g. 'UnifiedUser').",
    )
    app_label = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Django app label (e.g. 'authentication').",
    )
    total_created = models.PositiveBigIntegerField(
        default=0,
        help_text="Cumulative records ever created. Never decrements.",
    )
    total_active = models.PositiveBigIntegerField(
        default=0,
        help_text="Records currently alive (is_deleted=False).",
    )
    total_updated = models.PositiveBigIntegerField(
        default=0,
        help_text=(
            "Cumulative update (save) operations on existing records. "
            "Captures every vendor/client field change."
        ),
    )
    total_soft_deleted = models.PositiveBigIntegerField(
        default=0,
        help_text="Records currently soft-deleted (recoverable).",
    )
    total_hard_deleted = models.PositiveBigIntegerField(
        default=0,
        help_text="Cumulative permanently purged records. Never decrements.",
    )
    total_records = models.PositiveBigIntegerField(
        default=0,
        help_text=(
            "Live count of ALL rows in the DB (active + soft-deleted). "
            "Decrements on hard-delete. Use for real-time capacity reports."
        ),
    )
    total_lifetime_records = models.PositiveBigIntegerField(
        default=0,
        help_text=(
            "Monotonically increasing. NEVER decrements. Counts every row "
            "ever inserted since first migration — the ultimate source of "
            "truth for 'how many X have ever used our platform?'"
        ),
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="Last counter mutation timestamp.",
    )

    class Meta:
        verbose_name = "Model Analytics"
        verbose_name_plural = "Model Analytics"
        # ordering = ['model_name']
        ordering = ['-last_updated']

    def __str__(self):
        return (
            "%s — created=%d active=%d upd=%d "
            "soft=%d hard=%d"
        ) % (
            self.model_name,
            self.total_created,
            self.total_active,
            self.total_updated,
            self.total_soft_deleted,
            self.total_hard_deleted,
        )

    # ----------------------------------------------------------------
    # Core mutation — atomic, select_for_update, race-condition safe
    # ----------------------------------------------------------------

    @classmethod
    def _adjust(cls, model_name, app_label='', **deltas):
        """
        Atomically apply ``deltas`` to the counter row for
        ``model_name`` using a race-condition-safe pattern:

        1. Attempt a direct F()-expression UPDATE on the existing
           row.  F() expressions translate to a single atomic
           ``UPDATE ... SET col = col + N`` — no read-modify-write
           race.
        2. If 0 rows were updated (row doesn't exist yet) perform
           ``get_or_create`` inside ``transaction.atomic()``.
           An ``IntegrityError`` from the duplicate-key race
           is caught and the UPDATE is retried, making the whole
           operation correct under any concurrency level.

        Why NOT ``select_for_update().get_or_create()``?
        -------------------------------------------------
        ``select_for_update`` issues a ``SELECT ... FOR UPDATE``
        but the FOR UPDATE lock only applies to an **existing**
        row.  When the row is absent both concurrent workers see
        "0 rows" and both try an INSERT → ``IntegrityError``.
        This new pattern avoids that two-phase race entirely.

        Args:
            model_name (str): Django model class name.
            app_label  (str): Django app label.
            **deltas   (int): Field-name → integer delta. Negatives
                decrement (clamped to 0 at the DB level via CASE).
        """
        from django.db import IntegrityError, transaction
        from django.db.models import F, Value
        from django.db.models.functions import Greatest

        with transaction.atomic():
            # ── Step 1: optimistic F()-expression UPDATE ──────────
            update_kwargs = {}
            for field, delta in deltas.items():
                # Clamp at 0: never store a negative count.
                update_kwargs[field] = Greatest(
                    F(field) + Value(delta), Value(0)
                )
            rows = cls.objects.filter(
                model_name=model_name,
            ).update(**update_kwargs)

            if rows == 0:
                # ── Step 2: row absent — create it ────────────────
                try:
                    cls.objects.create(
                        model_name=model_name,
                        app_label=app_label,
                        **{k: max(v, 0) for k, v in deltas.items()},
                    )
                except IntegrityError:
                    # Another worker created the row between our
                    # UPDATE (0 rows) and this INSERT — just retry
                    # the UPDATE which will now find the row.
                    cls.objects.filter(
                        model_name=model_name,
                    ).update(**update_kwargs)
            elif app_label:
                # Ensure app_label is set (idempotent).
                cls.objects.filter(
                    model_name=model_name,
                    app_label='',
                ).update(app_label=app_label)

        logger.debug(
            "ModelAnalytics[%s] adjusted: %s",
            model_name,
            deltas,
        )

    @classmethod
    async def _aadjust(cls, model_name, app_label='', **deltas):
        """
        Async evaluation of _adjust.
        """
        from django.db import IntegrityError
        from django.db.models import F, Value
        from django.db.models.functions import Greatest

        update_kwargs = {}
        for field, delta in deltas.items():
            update_kwargs[field] = Greatest(
                F(field) + Value(delta), Value(0)
            )
            
        rows = await cls.objects.filter(
            model_name=model_name,
        ).aupdate(**update_kwargs)

        if rows == 0:
            try:
                await cls.objects.acreate(
                    model_name=model_name,
                    app_label=app_label,
                    **{k: max(v, 0) for k, v in deltas.items()},
                )
            except IntegrityError:
                await cls.objects.filter(
                    model_name=model_name,
                ).aupdate(**update_kwargs)
        elif app_label:
            await cls.objects.filter(
                model_name=model_name,
                app_label='',
            ).aupdate(app_label=app_label)

        logger.debug(
            "ModelAnalytics[%s] adjusted async: %s",
            model_name,
            deltas,
        )

    # ----------------------------------------------------------------
    # High-level event helpers (called from signals / admin mixins)
    # Each method dispatches a Celery task via on_commit so it
    # NEVER blocks the request thread.
    # ----------------------------------------------------------------

    @classmethod
    def _dispatch(cls, model_name, app_label, **deltas):
        """
        Schedule ``_adjust`` as a fire-and-forget background task.

        Transaction-safety
        ------------------
        When called from within a DB transaction (HTTP view, admin
        action, model signal), wraps the Celery dispatch in
        ``transaction.on_commit()`` so the counter mutates ONLY
        after the outer transaction commits — preventing phantom
        increments on rollbacks.

        Async/Celery-task safety
        ------------------------
        When called from INSIDE a Celery task there is no outer
        Django transaction (Celery autocommit mode) so
        ``on_commit`` fires immediately — this is correct.

        Broker-down fallback
        --------------------
        If the Celery broker (Redis) is unreachable, falls back
        to a direct synchronous ``_adjust()`` call so no counts
        are permanently lost.
        """
        try:
            from django.db import transaction as _tx
            from apps.common.tasks import update_model_analytics_counter

            def _fire():
                try:
                    update_model_analytics_counter.apply_async(
                        kwargs={
                            'model_name': model_name,
                            'app_label': app_label,
                            'deltas': deltas,
                        },
                        retry=False,
                        ignore_result=True,
                    )
                except Exception:  # noqa: BLE001
                    # Broker down fallback — synchronous update.
                    try:
                        cls._adjust(
                            model_name,
                            app_label=app_label,
                            **deltas,
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "ModelAnalytics sync fallback failed "
                            "for %s",
                            model_name,
                        )

            _tx.on_commit(_fire)

        except Exception:  # noqa: BLE001
            logger.warning(
                "ModelAnalytics._dispatch failed for %s",
                model_name,
            )

    @classmethod
    def record_created(cls, model_name, app_label='', count=1):
        """
        Call when ``count`` new records are created.

        Increments:
          - total_created (+count): cumulative inserts, never decrements.
          - total_active (+count): live active records.
          - total_records (+count): live DB row count (active + soft-deleted).
          - total_lifetime_records (+count): the eternal all-time counter.
        """
        cls._dispatch(
            model_name, app_label,
            total_created=+count,
            total_active=+count,
            total_records=+count,
            total_lifetime_records=+count,
        )

    @classmethod
    def record_updated(cls, model_name, app_label='', count=1):
        """
        Call when ``count`` existing records are updated
        (``post_save`` with ``created=False``).

        ``total_updated`` increments monotonically — it captures
        every field change made by vendors, clients, or admins.
        It does NOT affect any other counter.
        """
        cls._dispatch(
            model_name, app_label,
            total_updated=+count,
        )

    @classmethod
    def record_soft_deleted(cls, model_name, app_label='', count=1):
        """
        Call when ``count`` records are soft-deleted.

        Moves active → soft_deleted. total_records unchanged
        (row still exists in DB). total_lifetime_records unchanged.
        """
        cls._dispatch(
            model_name, app_label,
            total_soft_deleted=+count,
            total_active=-count,
        )

    @classmethod
    def record_restored(cls, model_name, app_label='', count=1):
        """
        Call when ``count`` soft-deleted records are restored.

        Moves soft_deleted → active. total_records unchanged.
        total_lifetime_records unchanged.
        """
        cls._dispatch(
            model_name, app_label,
            total_soft_deleted=-count,
            total_active=+count,
        )

    @classmethod
    def record_hard_deleted(
        cls, model_name, app_label='', count=1, was_soft_deleted=False
    ):
        """
        Call when ``count`` records are permanently deleted.

        ``total_lifetime_records`` is NEVER touched here — it must
        remain the eternal source of truth ("ever existed").
        ``total_records`` decrements because the physical row is gone.

        Args:
            was_soft_deleted (bool): If True the record was already
                soft-deleted (so decrement soft_deleted instead of
                active).
        """
        if was_soft_deleted:
            cls._dispatch(
                model_name, app_label,
                total_soft_deleted=-count,
                total_hard_deleted=+count,
                total_records=-count,
            )
        else:
            cls._dispatch(
                model_name, app_label,
                total_active=-count,
                total_hard_deleted=+count,
                total_records=-count,
            )

    @classmethod
    def record_seeded(
        cls, model_name, app_label='',
        total_active=0, total_soft_deleted=0,
        total_created=0, total_updated=0, total_hard_deleted=0,
    ):
        """
        Bootstrap / seed a ModelAnalytics row from real DB counts.

        Called by the ``seed_model_analytics`` management command.
        Safe to call multiple times (upsert pattern). Overwrites
        all counters based on live DB counts so drift is corrected.

        Args:
            total_active        int: COUNT(*) WHERE is_deleted=False.
            total_soft_deleted  int: COUNT(*) WHERE is_deleted=True.
            total_created       int: total_active + total_soft_deleted
                                    + total_hard_deleted (if available).
            total_hard_deleted  int: inferred from existing row if possible.
        """
        total_records_now = total_active + total_soft_deleted
        # total_lifetime = total_created (if available) else total_records
        total_lifetime = total_created if total_created else total_records_now

        cls.objects.update_or_create(
            model_name=model_name,
            defaults=dict(
                app_label=app_label,
                total_active=total_active,
                total_soft_deleted=total_soft_deleted,
                total_created=total_created or total_records_now,
                total_updated=total_updated,
                total_hard_deleted=total_hard_deleted,
                total_records=total_records_now,
                total_lifetime_records=total_lifetime,
            ),
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


# ================================================================
# 6. USER LIFECYCLE REGISTRY
#    Permanent, append-only audit table for every user identity
#    ever created on the Fashionistar platform.
#    NEVER soft-deleted, NEVER hard-deleted.
#    Persists even after a UnifiedUser is hard-purged from the DB.
# ================================================================

class UserLifecycleRegistry(models.Model):
    """
    Permanent, delete-proof audit log for every user identity ever
    created on the Fashionistar platform.

    Design Goals
    ------------
    1. **Permanence** — This table uses ``models.Manager()`` (NOT the
       soft-delete manager). Rows are NEVER deleted, even when the
       corresponding ``UnifiedUser`` record is hard-purged.

    2. **Analytics** — Tracks total signups, countries, login counts,
       and lifecycle events for financial decisions and marketing.

    3. **Audit compliance** — Provides a complete record of who was on
       the platform, even after GDPR hard-delete of the live account.

    4. **Background-only writes** — All mutations go through the
       ``update_user_lifecycle_registry`` Celery task so the HTTP
       request path is never blocked. Written via post-save signal after
       transaction commit.

    Identity equation (always true)
    --------------------------------
        total_users_ever = active + soft_deleted + hard_deleted

    Usage (read-only in admin)
    --------------------------
        UserLifecycleRegistry.objects.filter(country='NG').count()
        UserLifecycleRegistry.objects.filter(status='hard_deleted').count()

    Note: ``objects`` intentionally uses the DEFAULT Django manager
    (not SoftDeleteManager) so every row is always visible.
    """

    # ── Status choices ──────────────────────────────────────────────
    STATUS_ACTIVE       = 'active'
    STATUS_SOFT_DELETED = 'soft_deleted'
    STATUS_HARD_DELETED = 'hard_deleted'
    STATUS_CHOICES = [
        (STATUS_ACTIVE,       'Active'),
        (STATUS_SOFT_DELETED, 'Soft Deleted (Recoverable)'),
        (STATUS_HARD_DELETED, 'Hard Deleted (Permanent)'),
    ]

    # ── Source choices ──────────────────────────────────────────────
    SOURCE_WEB            = 'web'
    SOURCE_MOBILE_IOS     = 'mobile_ios'
    SOURCE_MOBILE_ANDROID = 'mobile_android'
    SOURCE_API            = 'api'
    SOURCE_CHOICES = [
        (SOURCE_WEB,            'Web Browser'),
        (SOURCE_MOBILE_IOS,     'Mobile (iOS)'),
        (SOURCE_MOBILE_ANDROID, 'Mobile (Android)'),
        (SOURCE_API,            'Direct API'),
    ]

    # ── Primary key ─────────────────────────────────────────────────
    id = models.UUIDField(
        primary_key=True,
        default=uuid6.uuid7,
        editable=False,
        help_text="UUID7 — globally unique, time-ordered.",
    )

    # ── Identity — snapshot at registration time ─────────────────────
    user_uuid = models.UUIDField(
        unique=True,          # DB-level uniqueness — prevents concurrent Celery duplicates
        db_index=True,
        help_text=(
            "UnifiedUser.pk at time of registration. "
            "Preserved even after the live account is hard-deleted. "
            "UNIQUE: one registry row per user ever created."
        ),
    )
    member_id = models.CharField(
        max_length=20,
        blank=True,
        default='',
        db_index=True,
        help_text="Fashionistar member ID (e.g. FASTAR000001).",
    )
    email = models.EmailField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Email address captured at registration. NOT unique — may be reused after hard-delete.",
    )
    phone = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        db_index=True,
        help_text="Phone (E.164 format) captured at registration.",
    )
    role = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text="User role at registration: admin, vendor, client.",
    )
    auth_provider = models.CharField(
        max_length=30,
        blank=True,
        default='email',
        help_text="Auth provider: email, google, facebook, apple, etc.",
    )

    # ── Geo at registration ──────────────────────────────────────────
    country = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text=(
            "Country at registration (from profile or IP geo-detection). "
            "Use for regional analytics and marketing campaigns."
        ),
    )
    state = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="State/Province at registration.",
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="City at registration.",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address at registration (for geo-detection if user didn't set location).",
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_WEB,
        help_text="Registration channel: web, mobile_ios, mobile_android, api.",
    )

    # ── Timestamps ───────────────────────────────────────────────────
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this registry entry was created (~ user registration time).",
    )
    soft_deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the live account was soft-deleted. Null if never soft-deleted.",
    )
    hard_deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When the live account was permanently purged. "
            "Null if still in DB. Set even if account was previously soft-deleted."
        ),
    )
    restored_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Most recent restore timestamp (soft-delete reversed).",
    )
    last_login_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the most recent successful login.",
    )

    # ── Lifecycle state ──────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        help_text="Current lifecycle state of the user account.",
    )

    # ── Engagement metrics ───────────────────────────────────────────
    total_logins = models.PositiveBigIntegerField(
        default=0,
        help_text="Cumulative successful login count. Never decrements.",
    )

    # ── Manager: plain Django manager — NO soft-delete filtering ─────
    objects = models.Manager()

    class Meta:
        verbose_name = "User Lifecycle Registry"
        verbose_name_plural = "User Lifecycle Registry"
        indexes = [
            models.Index(fields=['user_uuid'],      name='idx_ulr_user_uuid'),
            models.Index(fields=['email'],           name='idx_ulr_email'),
            models.Index(fields=['phone'],           name='idx_ulr_phone'),
            models.Index(fields=['country'],         name='idx_ulr_country'),
            models.Index(fields=['status'],          name='idx_ulr_status'),
            models.Index(fields=['created_at'],      name='idx_ulr_created'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"UserLifecycleRegistry("
            f"{self.email or self.phone or self.member_id} | "
            f"status={self.status} | "
            f"logins={self.total_logins})"
        )


# ================================================================
# 7. ENTITY LIFECYCLE REGISTRY (Abstract mixin)
#    Reusable pattern for Vendor, Product, Order, Category,
#    Collection, Payment, and any other critical platform entity.
# ================================================================

class EntityLifecycleRegistry(models.Model):
    """
    Abstract, permanent lifecycle registry for any major platform entity.

    Extend this for:
        - VendorLifecycleRegistry  (apps/vendors or apps/common)
        - ProductLifecycleRegistry (apps/products)
        - OrderLifecycleRegistry   (apps/orders)
        - CategoryLifecycleRegistry
        - CollectionLifecycleRegistry
        - PaymentLifecycleRegistry

    Design
    ------
    * One row per entity identity, NEVER deleted.
    * FK-free: stores entity_uuid + entity_type as strings so the
      row survives even after hard-delete of the source row.
    * Source maps to the source model: 'Vendor', 'Product', 'Order',
      'Category', 'Collection', 'Payment', etc.
    * All mutations go through Celery background tasks.

    Usage example (for Vendor)
    --------------------------
        class VendorLifecycleRegistry(EntityLifecycleRegistry):
            class Meta(EntityLifecycleRegistry.Meta):
                verbose_name = "Vendor Lifecycle Registry"

    Then wire post-save signal in apps/vendors/signals.py:
        @receiver(post_save, sender=Vendor)
        def on_vendor_saved(sender, instance, created, **kwargs):
            if created:
                transaction.on_commit(
                    lambda: upsert_entity_lifecycle_registry.delay(
                        entity_type='Vendor',
                        entity_uuid=str(instance.pk),
                        ...
                    )
                )
    """

    # ── Status choices (shared with UserLifecycleRegistry) ──────────
    STATUS_ACTIVE       = 'active'
    STATUS_SOFT_DELETED = 'soft_deleted'
    STATUS_HARD_DELETED = 'hard_deleted'
    STATUS_CHOICES = [
        (STATUS_ACTIVE,       'Active'),
        (STATUS_SOFT_DELETED, 'Soft Deleted (Recoverable)'),
        (STATUS_HARD_DELETED, 'Hard Deleted (Permanent)'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid6.uuid7,
        editable=False,
    )
    entity_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Model class name: 'Vendor', 'Product', 'Order', etc.",
    )
    entity_uuid = models.UUIDField(
        db_index=True,
        help_text="PK of the original entity at creation time.",
    )
    owner_user_uuid = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="UnifiedUser.pk of the entity owner/creator.",
    )

    # ── Geo at creation ──────────────────────────────────────────────
    country = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    state   = models.CharField(max_length=100, blank=True, null=True)
    city    = models.CharField(max_length=100, blank=True, null=True)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at      = models.DateTimeField(auto_now_add=True)
    soft_deleted_at = models.DateTimeField(null=True, blank=True)
    hard_deleted_at = models.DateTimeField(null=True, blank=True)
    restored_at     = models.DateTimeField(null=True, blank=True)

    # ── State ────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )

    # ── Extra metadata (flexible JSON for any entity-specific data) ──
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Flexible entity-specific snapshot data. "
            "E.g. for Product: {'sku': '...', 'price': '...', 'category': '...'}"
        ),
    )

    # ── Manager: permanent, no soft-delete filtering ─────────────────
    objects = models.Manager()

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['entity_type', 'entity_uuid'], name='idx_elr_entity'),
            models.Index(fields=['owner_user_uuid'],             name='idx_elr_owner'),
            models.Index(fields=['country'],                     name='idx_elr_country'),
            models.Index(fields=['status'],                      name='idx_elr_status'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"EntityLifecycleRegistry("
            f"type={self.entity_type} | "
            f"uuid={str(self.entity_uuid)[:8]}... | "
            f"status={self.status})"
        )



__all__ = [
    'TimeStampedModel',
    'SoftDeleteModel',
    'DeletedRecords',
    'DeletionAuditCounter',
    'ModelAnalytics',
    'HardDeleteMixin',
    'UserLifecycleRegistry',
    'EntityLifecycleRegistry',
]
