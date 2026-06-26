# apps/common/models/analytics.py
"""
Platform-wide record lifecycle analytics for the Fashionistar platform.

Architecture:
    ModelAnalytics         — One row per Django model. Tracks total_created,
                             total_active, total_soft_deleted, total_hard_deleted,
                             total_updated, total_records, and total_lifetime_records
                             counters. All mutations are atomic (F() expressions) and
                             fire-and-forget via Celery / ``transaction.on_commit()``.
    UserLifecycleRegistry  — Permanent, append-only audit table for every user identity
                             ever created. Survives even after ``UnifiedUser`` hard-delete.
    EntityLifecycleRegistry — Abstract pattern for Vendor, Product, Order, Category, etc.

Design Principles:
    - All counter mutations go through ``_adjust()`` or ``_dispatch()`` — never raw
      ``update()`` calls from signal handlers, to ensure broker-down safety.
    - ``transaction.on_commit()`` prevents phantom counter increments on rollback.
    - Race-condition safety via ``F()`` expressions (no read-modify-write cycles).
    - UserLifecycleRegistry uses the plain Django manager (NOT SoftDeleteManager) so
      every row is always visible regardless of soft-delete state.
"""

import logging

import uuid6
from django.db import models

logger = logging.getLogger(__name__)


# ================================================================
# 1. MODEL ANALYTICS — Global Record Counter
# ================================================================

class ModelAnalytics(models.Model):
    """Global analytics table: one row per Django model.

    Tracks the complete lifecycle of every record across the entire
    platform through atomic counter columns.

    Counter Invariant:
        total_lifetime_records is monotonically increasing and NEVER
        decrements regardless of soft-delete or hard-delete.

        Identity equation (always true):
            total_created == total_active + total_soft_deleted
                          + total_hard_deleted

    Race-Condition Safety:
        All mutations go through ``_adjust()`` which uses F() expressions
        (a single atomic SQL UPDATE) — no read-modify-write races under
        100K+ concurrent requests.

    Performance:
        Mutations are dispatched as fire-and-forget Celery tasks via
        ``transaction.on_commit()`` so the hot path of every model
        save/delete is NEVER slowed down.

    Access:
        Superadmin-only read-only admin dashboard.

    Attributes:
        model_name: Django model class name (e.g. ``'UnifiedUser'``).
        app_label: Django app label (e.g. ``'authentication'``).
        total_created: Cumulative records ever created. Never decrements.
        total_active: Records currently alive (``is_deleted=False``).
        total_updated: Cumulative update operations on existing records.
        total_soft_deleted: Records currently soft-deleted (recoverable).
        total_hard_deleted: Cumulative permanently purged records.
        total_records: Live DB row count (active + soft-deleted).
        total_lifetime_records: Monotonically increasing all-time counter.
        last_updated: Auto-updated timestamp of the last counter mutation.
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
        ordering = ['-last_updated']

    def __str__(self) -> str:
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
    # Core mutation — atomic, F()-expression, race-condition safe
    # ----------------------------------------------------------------

    @classmethod
    def _adjust(cls, model_name: str, app_label: str = '', **deltas: int) -> None:
        """Atomically apply ``deltas`` to the counter row for ``model_name``.

        Uses a race-condition-safe two-step pattern:

        1. Attempt a direct F()-expression UPDATE on the existing row.
           F() expressions translate to a single atomic
           ``UPDATE ... SET col = col + N`` — no read-modify-write race.
        2. If 0 rows were updated (row doesn't exist yet) perform
           ``get_or_create`` inside ``transaction.atomic()``.  An
           ``IntegrityError`` from the duplicate-key race is caught and
           the UPDATE is retried — making the whole operation correct
           under any concurrency level.

        Why NOT ``select_for_update().get_or_create()``?
            ``select_for_update`` issues a FOR UPDATE lock only on an
            **existing** row.  When the row is absent both concurrent
            workers see "0 rows" and both try an INSERT →
            ``IntegrityError``.  This two-step F()-expression pattern
            avoids that race entirely.

        Args:
            model_name: Django model class name.
            app_label: Django app label.
            **deltas: Field-name → integer delta. Negatives decrement
                (clamped to 0 at the DB level via CASE/Greatest).
        """
        from django.db import IntegrityError, transaction
        from django.db.models import F, Value
        from django.db.models.functions import Greatest

        # ── Step 1: optimistic F()-expression UPDATE ──────────
        update_kwargs = {}
        for field, delta in deltas.items():
            update_kwargs[field] = Greatest(
                F(field) + Value(delta), Value(0)
            )
        rows = cls.objects.filter(
            model_name=model_name,
        ).update(**update_kwargs)

        if rows == 0:
            # ── Step 2: row absent — create it ────────────────
            try:
                with transaction.atomic():
                    cls.objects.create(
                        model_name=model_name,
                        app_label=app_label,
                        **{k: max(v, 0) for k, v in deltas.items()},
                    )
            except IntegrityError:
                # Another worker created the row between our
                # UPDATE (0 rows) and this INSERT — just retry.
                cls.objects.filter(
                    model_name=model_name,
                ).update(**update_kwargs)
        elif app_label:
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
    async def _aadjust(cls, model_name: str, app_label: str = '', **deltas: int) -> None:
        """Async variant of ``_adjust()``.

        Args:
            model_name: Django model class name.
            app_label: Django app label.
            **deltas: Field-name → integer delta.
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
    # Dispatch helper — wraps _adjust in a fire-and-forget Celery task
    # ----------------------------------------------------------------

    @classmethod
    def _dispatch(cls, model_name: str, app_label: str, **deltas: int) -> None:
        """Schedule ``_adjust`` as a fire-and-forget Celery background task.

        Transaction Safety:
            When called from within a DB transaction, wraps the Celery
            dispatch in ``transaction.on_commit()`` so the counter
            mutates ONLY after the outer transaction commits — preventing
            phantom increments on rollback.

        Broker-Down Fallback:
            If the Celery broker (Redis) is unreachable, falls back to a
            direct synchronous ``_adjust()`` call so no counts are
            permanently lost.

        Args:
            model_name: Django model class name.
            app_label: Django app label.
            **deltas: Field-name → integer delta passed through to
                ``_adjust``.
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

    # ----------------------------------------------------------------
    # High-level event helpers
    # ----------------------------------------------------------------

    @classmethod
    def record_created(cls, model_name: str, app_label: str = '', count: int = 1) -> None:
        """Record ``count`` new instances being created.

        Increments ``total_created``, ``total_active``, ``total_records``,
        and ``total_lifetime_records`` by ``count``.

        Args:
            model_name: Django model class name.
            app_label: Django app label.
            count: Number of records created (default 1).
        """
        cls._dispatch(
            model_name, app_label,
            total_created=+count,
            total_active=+count,
            total_records=+count,
            total_lifetime_records=+count,
        )

    @classmethod
    def record_updated(cls, model_name: str, app_label: str = '', count: int = 1) -> None:
        """Record ``count`` existing instances being updated.

        Only increments ``total_updated`` — no other counters change on
        an update event.

        Args:
            model_name: Django model class name.
            app_label: Django app label.
            count: Number of records updated (default 1).
        """
        cls._dispatch(
            model_name, app_label,
            total_updated=+count,
        )

    @classmethod
    def record_soft_deleted(cls, model_name: str, app_label: str = '', count: int = 1) -> None:
        """Record ``count`` instances being soft-deleted.

        Moves active → soft_deleted. ``total_records`` is unchanged
        (row still exists in DB). ``total_lifetime_records`` is
        unchanged.

        Args:
            model_name: Django model class name.
            app_label: Django app label.
            count: Number of records soft-deleted (default 1).
        """
        cls._dispatch(
            model_name, app_label,
            total_soft_deleted=+count,
            total_active=-count,
        )

    @classmethod
    def record_restored(cls, model_name: str, app_label: str = '', count: int = 1) -> None:
        """Record ``count`` soft-deleted instances being restored.

        Moves soft_deleted → active. ``total_records`` unchanged.

        Args:
            model_name: Django model class name.
            app_label: Django app label.
            count: Number of records restored (default 1).
        """
        cls._dispatch(
            model_name, app_label,
            total_soft_deleted=-count,
            total_active=+count,
        )

    @classmethod
    def record_hard_deleted(
        cls,
        model_name: str,
        app_label: str = '',
        count: int = 1,
        was_soft_deleted: bool = False,
    ) -> None:
        """Record ``count`` instances being permanently deleted.

        ``total_lifetime_records`` is NEVER touched — it must remain the
        eternal source of truth ("ever existed"). ``total_records``
        decrements because the physical row is gone.

        Args:
            model_name: Django model class name.
            app_label: Django app label.
            count: Number of records hard-deleted (default 1).
            was_soft_deleted: If ``True``, the record was already in a
                soft-deleted state (so decrement ``total_soft_deleted``
                instead of ``total_active``).
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
        cls,
        model_name: str,
        app_label: str = '',
        total_active: int = 0,
        total_soft_deleted: int = 0,
        total_created: int = 0,
        total_updated: int = 0,
        total_hard_deleted: int = 0,
    ) -> None:
        """Bootstrap a ModelAnalytics row from real live DB counts.

        Called by the ``seed_model_analytics`` management command. Safe
        to call multiple times (upsert pattern). Overwrites all counters
        based on live DB counts so drift is corrected.

        Args:
            model_name: Django model class name.
            app_label: Django app label.
            total_active: COUNT(*) WHERE is_deleted=False.
            total_soft_deleted: COUNT(*) WHERE is_deleted=True.
            total_created: total_active + total_soft_deleted
                + total_hard_deleted (if available).
            total_updated: Cumulative update count (from logs if
                available, else 0).
            total_hard_deleted: Inferred from existing row if possible.
        """
        total_records_now = total_active + total_soft_deleted
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
# 2. USER LIFECYCLE REGISTRY
#    Permanent, append-only audit table for every user identity
#    ever created on the Fashionistar platform.
# ================================================================

class UserLifecycleRegistry(models.Model):
    """Permanent, delete-proof audit log for every user identity.

    Design Goals:
        1. Permanence — This table uses ``models.Manager()`` (NOT the
           soft-delete manager). Rows are NEVER deleted, even when the
           corresponding ``UnifiedUser`` record is hard-purged.
        2. Analytics — Tracks total signups, countries, login counts,
           and lifecycle events for financial decisions and marketing.
        3. Audit Compliance — Provides a complete record of who was on
           the platform, even after GDPR hard-delete of the live account.
        4. Background-only writes — All mutations go through the
           ``update_user_lifecycle_registry`` Celery task so the HTTP
           request path is never blocked.

    Identity Equation (always true):
        total_users_ever == active + soft_deleted + hard_deleted

    Usage:
        UserLifecycleRegistry.objects.filter(country='NG').count()
        UserLifecycleRegistry.objects.filter(status='hard_deleted').count()

    Note:
        ``objects`` intentionally uses the DEFAULT Django manager (not
        SoftDeleteManager) so every row is always visible.
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
        unique=True,
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
        max_length=100, blank=True, null=True, db_index=True,
        help_text="Country at registration (from profile or IP geo-detection).",
    )
    state = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="State/Province at registration.",
    )
    city = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="City at registration.",
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
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
        null=True, blank=True,
        help_text="When the live account was soft-deleted. Null if never soft-deleted.",
    )
    hard_deleted_at = models.DateTimeField(
        null=True, blank=True,
        help_text=(
            "When the live account was permanently purged. "
            "Null if still in DB. Set even if account was previously soft-deleted."
        ),
    )
    restored_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Most recent restore timestamp (soft-delete reversed).",
    )
    last_login_at = models.DateTimeField(
        null=True, blank=True,
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
            models.Index(fields=['user_uuid'],  name='idx_ulr_user_uuid'),
            models.Index(fields=['email'],       name='idx_ulr_email'),
            models.Index(fields=['phone'],       name='idx_ulr_phone'),
            models.Index(fields=['country'],     name='idx_ulr_country'),
            models.Index(fields=['status'],      name='idx_ulr_status'),
            models.Index(fields=['created_at'],  name='idx_ulr_created'),
        ]
        ordering = ['-created_at']

    def __str__(self) -> str:
        return (
            f"UserLifecycleRegistry("
            f"{self.email or self.phone or self.member_id} | "
            f"status={self.status} | "
            f"logins={self.total_logins})"
        )


# ================================================================
# 3. ENTITY LIFECYCLE REGISTRY (Abstract mixin)
# ================================================================

class EntityLifecycleRegistry(models.Model):
    """Abstract permanent lifecycle registry for any major platform entity.

    Extend this for:
        - VendorLifecycleRegistry  (apps/vendors or apps/common)
        - ProductLifecycleRegistry (apps/products)
        - OrderLifecycleRegistry   (apps/orders)
        - CategoryLifecycleRegistry
        - CollectionLifecycleRegistry
        - PaymentLifecycleRegistry

    Design:
        - One row per entity identity, NEVER deleted.
        - FK-free: stores entity_uuid + entity_type as strings so the
          row survives even after hard-delete of the source row.
        - All mutations go through Celery background tasks.

    Usage:
        class VendorLifecycleRegistry(EntityLifecycleRegistry):
            class Meta(EntityLifecycleRegistry.Meta):
                verbose_name = "Vendor Lifecycle Registry"

        # Wire post_save signal in apps/vendors/signals.py:
        @receiver(post_save, sender=Vendor)
        def on_vendor_saved(sender, instance, created, **kwargs):
            if created:
                transaction.on_commit(
                    lambda: upsert_entity_lifecycle_registry.delay(
                        entity_type='Vendor',
                        entity_uuid=str(instance.pk),
                    )
                )
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

    # ── Extra metadata (flexible JSON) ──────────────────────────────
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

    def __str__(self) -> str:
        return (
            f"EntityLifecycleRegistry("
            f"type={self.entity_type} | "
            f"uuid={str(self.entity_uuid)[:8]}... | "
            f"status={self.status})"
        )


__all__ = [
    "ModelAnalytics",
    "UserLifecycleRegistry",
    "EntityLifecycleRegistry",
]
