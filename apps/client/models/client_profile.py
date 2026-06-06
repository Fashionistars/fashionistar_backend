# apps/client/models/client_profile.py
"""
ClientProfile — 1:1 Profile for role='client' users.

MIGRATION NOTE: Originally in apps.authentication.models.client_profile.
Moved here as part of Phase 2 domain-driven architecture migration.

The `db_table` is intentionally kept as 'client_profile'
to avoid a destructive DB rename migration.

Architecture:
  ─ All database-level read helpers live HERE on the model as classmethods.
  ─ Selectors (selectors/client_selectors.py) are thin delegators — they
    call these classmethods instead of repeating ORM logic.
  ─ This pattern offloads computation to the DB (joins / aggregates) rather
    than Python serializers or API views.

Reverse-relationship cheat-sheet (all usable in sync DRF and async Ninja):
  user.client_profile               → ClientProfile (OneToOne)
  user.user_orders.filter(...)      → Order rows for this client
  user.product_wishlists.filter(...)→ ProductWishlist rows
  profile.client_addresses.filter() → ClientAddress rows
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import models, transaction
from django.db.models import Count, F, Prefetch, Sum

from apps.common.models import TimeStampedModel, SoftDeleteModel

logger = logging.getLogger(__name__)


class ClientProfile(TimeStampedModel, SoftDeleteModel):
    """
    Extended profile for client-role users.

    Linked 1:1 to UnifiedUser (role='client').
    Stores shopping preferences, shipping defaults, style data,
    and spend/order analytics.

    Access:
        user.client_profile  — reverse OneToOne relation
        ClientProfile.objects.get(user=user) — direct lookup
    """

    # ── Identity link ──────────────────────────────────────────────
    user = models.OneToOneField(
        "authentication.UnifiedUser",
        on_delete=models.CASCADE,
        related_name="client_profile",
        limit_choices_to={"role": "client"},
        help_text="The client user this profile belongs to.",
    )

    # ── Personal Details ───────────────────────────────────────────
    bio = models.TextField(
        blank=True,
        default="",
        max_length=500,
        help_text="Short personal bio (max 500 chars).",
    )

    # ── Shipping / Location ────────────────────────────────────────
    default_shipping_address = models.TextField(
        blank=True,
        default="",
        help_text="Default shipping address for checkout.",
    )
    state = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="Nigeria")

    # ── Style & Size Preferences ───────────────────────────────────
    SIZE_CHOICES = [
        ("XS", "XS"),
        ("S", "S"),
        ("M", "M"),
        ("L", "L"),
        ("XL", "XL"),
        ("XXL", "XXL"),
        ("XXXL", "XXXL"),
    ]
    preferred_size = models.CharField(
        max_length=10,
        choices=SIZE_CHOICES,
        blank=True,
        default="",
        help_text="Preferred clothing size.",
    )
    style_preferences = models.JSONField(
        default=list,
        blank=True,
        help_text='Style tags: ["casual", "afrocentric", "formal"]. Used by AI engine.',
    )
    favourite_colours = models.JSONField(
        default=list,
        blank=True,
        help_text="Favourite colour hex codes or names.",
    )

    # ── Shopping Behaviour ─────────────────────────────────────────
    total_orders = models.PositiveIntegerField(default=0)
    total_spent_ngn = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    # ── Profile Completeness ───────────────────────────────────────
    is_profile_complete = models.BooleanField(
        default=False,
        help_text="True once size, address, and style preferences are filled in.",
    )

    # ── Notification preferences ──────────────────────────────────
    email_notifications_enabled = models.BooleanField(
        default=True,
        help_text="Receive order and promo email notifications.",
    )
    sms_notifications_enabled = models.BooleanField(
        default=False,
        help_text="Receive SMS alerts for order updates.",
    )

    # ── Phase 12: 2026+ Scale Fields ────────────────────────────────────────
    # Loyalty Programme
    TIER_STANDARD = "standard"
    TIER_SILVER = "silver"
    TIER_GOLD = "gold"
    TIER_PLATINUM = "platinum"
    LOYALTY_TIER_CHOICES = [
        (TIER_STANDARD, "Standard"),
        (TIER_SILVER, "Silver"),
        (TIER_GOLD, "Gold"),
        (TIER_PLATINUM, "Platinum"),
    ]
    loyalty_tier = models.CharField(
        max_length=12, choices=LOYALTY_TIER_CHOICES, default=TIER_STANDARD, db_index=True,
    )
    loyalty_points = models.PositiveIntegerField(
        default=0,
        help_text="Redeemable loyalty points (100 pts = ₦1).",
    )
    referral_code = models.CharField(
        max_length=20, blank=True, null=True, unique=True, db_index=True,
        help_text="Client's unique referral code for inviting friends.",
    )
    referral_count = models.PositiveIntegerField(default=0)

    # AI & Personalisation
    ai_style_embedding = models.JSONField(
        null=True, blank=True,
        help_text="768-dim style embedding vector for personalised product recommendations.",
    )
    occasion_preferences = models.JSONField(
        default=list, blank=True,
        help_text='Occasion tags: ["wedding", "casual", "office", "traditional"].',
    )
    body_type = models.CharField(
        max_length=30, blank=True,
        choices=[
            ("slim", "Slim"), ("athletic", "Athletic"), ("curvy", "Curvy"),
            ("plus_size", "Plus Size"), ("petite", "Petite"), ("tall", "Tall"),
        ],
        help_text="Body type for fit-based AI recommendations.",
    )

    # Measurements Integration
    default_measurement_profile = models.ForeignKey(
        "measurements.MeasurementProfile", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="default_measurement_for_clients",
        help_text="The client's active measurement profile for size recommendations.",
    )

    # GDPR & Data Portability
    data_portability_requested_at = models.DateTimeField(
        null=True, blank=True,
        help_text="GDPR Article 20 — timestamp of last data portability export request.",
    )

    class Meta:
        verbose_name = "Client Profile"
        verbose_name_plural = "Client Profiles"
        db_table = "client_profile"
        indexes = [
            models.Index(fields=["user"], name="client_profile_user_idx"),
            models.Index(fields=["country"], name="client_profile_country_idx"),
            models.Index(fields=["loyalty_tier"], name="cp_loyalty_tier_idx"),
            models.Index(fields=["referral_code"], name="cp_referral_idx"),
        ]

    def __str__(self) -> str:
        identifier = (
            getattr(self.user, "email", None)
            or getattr(self.user, "phone", None)
            or str(self.user.pk)
        )
        return f"ClientProfile({identifier})"

    # ══════════════════════════════════════════════════════════════
    #  PROFILE COMPLETENESS
    # ══════════════════════════════════════════════════════════════

    def update_completeness(self) -> None:
        """Recalculates is_profile_complete and saves if changed."""
        complete = all(
            [
                self.preferred_size,
                self.default_shipping_address,
                bool(self.style_preferences),
            ]
        )
        if self.is_profile_complete != complete:
            self.is_profile_complete = complete
            self.save(update_fields=["is_profile_complete", "updated_at"])

    # ══════════════════════════════════════════════════════════════
    #  SHOPPING ANALYTICS (atomic DB helpers)
    # ══════════════════════════════════════════════════════════════

    def increment_orders(self, amount_ngn: float | int = 0) -> None:
        """
        Atomically increment total_orders and total_spent_ngn.
        Safe under concurrent load — uses F() expressions so there
        is never a read-modify-write race condition.

        Args:
            amount_ngn: Order total in NGN to add to running total.
        """
        try:
            type(self).objects.filter(pk=self.pk).update(
                total_orders=F("total_orders") + 1,
                total_spent_ngn=F("total_spent_ngn") + amount_ngn,
            )
            self.refresh_from_db(fields=["total_orders", "total_spent_ngn"])
        except Exception:
            logger.exception("Failed to increment orders for ClientProfile %s", self.pk)

    # ══════════════════════════════════════════════════════════════
    #  DATABASE-LEVEL QUERY HELPERS (SYNC)
    #
    #  These methods are the canonical single-query entry points.
    #  Selectors call these — they do NOT duplicate ORM logic.
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def get_or_create_for_user(cls, user) -> "ClientProfile":
        """
        Idempotent — returns existing profile or creates a blank one.

        Uses select_for_update() inside a transaction.atomic() block to guard
        against race conditions when two concurrent requests trigger profile
        creation simultaneously (e.g. simultaneous login from two devices).

        Args:
            user: UnifiedUser instance.

        Returns:
            ClientProfile instance (guaranteed to be exactly one per user).
        """
        with transaction.atomic():
            profile, _ = cls.objects.select_for_update().get_or_create(user=user)
            return profile

    @classmethod
    def get_stats_for_user(cls, user) -> dict[str, Any]:
        """
        Single-query stats for the JWT token response (login payload).

        Traversal: ClientProfile → scalar fields only (no joins needed).
        Returns a .values() dict so no Python object is instantiated.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            dict with total_orders, total_spent_ngn, is_profile_complete,
            preferred_size.  Defaults to zeros if profile does not exist.
        """
        try:
            return (
                cls.objects.filter(user=user)
                .values(
                    "total_orders",
                    "total_spent_ngn",
                    "is_profile_complete",
                    "preferred_size",
                )
                .get()
            )
        except cls.DoesNotExist:
            return {
                "total_orders": 0,
                "total_spent_ngn": Decimal("0.00"),
                "is_profile_complete": False,
                "preferred_size": "",
            }

    @classmethod
    def get_address_list(cls, user) -> list[dict]:
        """
        Single DB round-trip: profile → addresses via reverse FK.

        Traversal: ClientProfile → ClientAddress (related_name="client_addresses").
        Uses .values() so no Python model instances are created.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            list[dict] ordered by default-first then most-recent.
            Empty list if profile or addresses not found.
        """
        try:
            from .client_address import ClientAddress

            return list(
                ClientAddress.objects.filter(client__user=user, is_deleted=False)
                .order_by("-is_default", "-created_at")
                .values(
                    "id",
                    "label",
                    "full_name",
                    "phone",
                    "street_address",
                    "city",
                    "state",
                    "country",
                    "postal_code",
                    "is_default",
                    "created_at",
                )
            )
        except Exception as exc:
            logger.error("get_address_list user=%s: %s", user, exc)
            return []

    @classmethod
    def get_order_stats_from_db(cls, user) -> dict[str, Any]:
        """
        Single aggregate query over user.user_orders reverse FK.

        Traversal: UnifiedUser.user_orders → Order.
        No profile lookup needed — goes directly from user to orders.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            dict with total_orders (int), total_spent_ngn (float),
            pending_count, active_count, completed_count.
        """
        from apps.order.models import OrderStatus

        try:
            qs = user.user_orders.all()
            agg = qs.aggregate(
                total_orders=Count("id"),
                total_spent_ngn=Sum("total_amount"),
            )
            pending_count = qs.filter(status=OrderStatus.PENDING_PAYMENT).count()
            active_count = qs.filter(
                status__in=[
                    OrderStatus.PAYMENT_CONFIRMED,
                    OrderStatus.PROCESSING,
                    OrderStatus.SHIPPED,
                    OrderStatus.OUT_FOR_DELIVERY,
                ]
            ).count()
            completed_count = qs.filter(
                status__in=[OrderStatus.COMPLETED, OrderStatus.DELIVERED]
            ).count()
            return {
                "total_orders": agg["total_orders"] or 0,
                "total_spent_ngn": float(agg["total_spent_ngn"] or 0),
                "pending_count": pending_count,
                "active_count": active_count,
                "completed_count": completed_count,
            }
        except Exception as exc:
            logger.error("get_order_stats_from_db user=%s: %s", user, exc)
            return {
                "total_orders": 0,
                "total_spent_ngn": 0.0,
                "pending_count": 0,
                "active_count": 0,
                "completed_count": 0,
            }

    @classmethod
    def get_wishlist_count(cls, user) -> int:
        """
        Single COUNT query over user.product_wishlists reverse FK.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            int — number of active wishlist entries.
        """
        try:
            return user.user_product_wishlists.count()
        except Exception as exc:
            logger.error("get_wishlist_count user=%s: %s", user, exc)
            return 0

    @classmethod
    def get_full_dashboard_snapshot(cls, user) -> dict[str, Any]:
        """
        Single-entry-point dashboard data for the client account page.

        Executes 4 DB queries total (profile, addresses, order stats, wishlist)
        using reverse FK traversal — NO N+1 loops in Python.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            dict with keys: profile, addresses, order_stats, wishlist_count.
        """
        try:
            profile = cls.objects.select_related("user").get(user=user)
        except cls.DoesNotExist:
            profile = cls.get_or_create_for_user(user)

        return {
            "profile": {
                "id": str(profile.pk),
                "bio": profile.bio,
                "state": profile.state,
                "country": profile.country,
                "preferred_size": profile.preferred_size,
                "style_preferences": profile.style_preferences,
                "favourite_colours": profile.favourite_colours,
                "total_orders": profile.total_orders,
                "total_spent_ngn": float(profile.total_spent_ngn),
                "is_profile_complete": profile.is_profile_complete,
                "email_notifications_enabled": profile.email_notifications_enabled,
                "sms_notifications_enabled": profile.sms_notifications_enabled,
            },
            "addresses": cls.get_address_list(user),
            "order_stats": cls.get_order_stats_from_db(user),
            "wishlist_count": cls.get_wishlist_count(user),
        }

    # ══════════════════════════════════════════════════════════════
    #  DATABASE-LEVEL QUERY HELPERS (ASYNC)
    #  Django 6.0 native async ORM — ZERO sync_to_async
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def aget_or_create_for_user(cls, user) -> "ClientProfile":
        """
        Idempotent — returns existing profile or creates a blank one.

        Async transactions are not supported by Django ORM. This async read-plane
        helper therefore uses the native ``aget_or_create()`` path only; contested
        profile provisioning remains in the sync service boundary.

        Args:
            user: UnifiedUser instance.

        Returns:
            ClientProfile instance (guaranteed to be exactly one per user).
        """
        profile, _ = await cls.objects.aget_or_create(user=user)
        return profile

    @classmethod
    async def aget_stats_for_user(cls, user) -> dict[str, Any]:
        """
        Async version of get_stats_for_user.

        Uses aget() — Django 6.0 native async ORM.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            dict with total_orders, total_spent_ngn, is_profile_complete,
            preferred_size.
        """
        try:
            return await (
                cls.objects.filter(user=user)
                .values(
                    "total_orders",
                    "total_spent_ngn",
                    "is_profile_complete",
                    "preferred_size",
                )
                .aget()
            )
        except cls.DoesNotExist:
            return {
                "total_orders": 0,
                "total_spent_ngn": Decimal("0.00"),
                "is_profile_complete": False,
                "preferred_size": "",
            }

    @classmethod
    async def aget_address_list(cls, user) -> list[dict]:
        """
        Async single DB round-trip: profile → addresses via reverse FK.

        Traversal: ClientProfile → ClientAddress (client_addresses).
        Uses async iteration — ZERO sync_to_async.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            list[dict] ordered by default-first then most-recent.
        """
        try:
            from .client_address import ClientAddress

            qs = (
                ClientAddress.objects.filter(client__user=user, is_deleted=False)
                .order_by("-is_default", "-created_at")
                .values(
                    "id",
                    "label",
                    "full_name",
                    "phone",
                    "street_address",
                    "city",
                    "state",
                    "country",
                    "postal_code",
                    "is_default",
                    "created_at",
                )
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_address_list user=%s: %s", user, exc)
            return []

    @classmethod
    async def aget_order_stats_from_db(cls, user) -> dict[str, Any]:
        """
        Async single aggregate query over user.user_orders reverse FK.

        Traversal: UnifiedUser → Order (related_name="user_orders").
        Uses aaggregate() + acount() — Django 6.0 native async ORM.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            dict with total_orders, total_spent_ngn, pending_count,
            active_count, completed_count.
        """
        from apps.order.models import OrderStatus

        try:
            qs = user.user_orders.all()
            agg = await qs.aaggregate(
                total_orders=Count("id"),
                total_spent_ngn=Sum("total_amount"),
            )
            pending_count = await qs.filter(status=OrderStatus.PENDING_PAYMENT).acount()
            active_count = await qs.filter(
                status__in=[
                    OrderStatus.PAYMENT_CONFIRMED,
                    OrderStatus.PROCESSING,
                    OrderStatus.SHIPPED,
                    OrderStatus.OUT_FOR_DELIVERY,
                ]
            ).acount()
            completed_count = await qs.filter(
                status__in=[OrderStatus.COMPLETED, OrderStatus.DELIVERED]
            ).acount()
            return {
                "total_orders": agg["total_orders"] or 0,
                "total_spent_ngn": float(agg["total_spent_ngn"] or 0),
                "pending_count": pending_count,
                "active_count": active_count,
                "completed_count": completed_count,
            }
        except Exception as exc:
            logger.error("aget_order_stats_from_db user=%s: %s", user, exc)
            return {
                "total_orders": 0,
                "total_spent_ngn": 0.0,
                "pending_count": 0,
                "active_count": 0,
                "completed_count": 0,
            }

    @classmethod
    async def aget_wishlist_count(cls, user) -> int:
        """
        Async COUNT query over user.product_wishlists reverse FK.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            int — number of active wishlist entries.
        """

        try:
            return await user.user_product_wishlists.acount()
        except Exception as exc:
            logger.error("aget_wishlist_count user=%s: %s", user, exc)
            return 0

    @classmethod
    async def aget_full_dashboard_snapshot(cls, user) -> dict[str, Any]:
        """
        Async entry-point for client dashboard — collects all profile data
        using 4 targeted DB queries, zero N+1.

        Order:
          1. ClientProfile aget() with select_related("user")
          2. ClientAddress async iteration (client_addresses reverse FK)
          3. Order aaggregate() + acount() per status bucket
          4. ProductWishlist acount()

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            dict with profile, addresses, order_stats, wishlist_count.
        """
        try:
            profile = await cls.objects.filter(user=user).select_related("user").aget()
        except cls.DoesNotExist:
            # Idempotent creation — sync path, acceptable on first-login only
            profile = await cls.aget_or_create_for_user(user)

        addresses, order_stats, wishlist_count = (
            await cls.aget_address_list(user),
            await cls.aget_order_stats_from_db(user),
            await cls.aget_wishlist_count(user),
        )

        return {
            "profile": {
                "id": str(profile.pk),
                "bio": profile.bio,
                "state": profile.state,
                "country": profile.country,
                "preferred_size": profile.preferred_size,
                "style_preferences": profile.style_preferences,
                "favourite_colours": profile.favourite_colours,
                "total_orders": profile.total_orders,
                "total_spent_ngn": float(profile.total_spent_ngn),
                "is_profile_complete": profile.is_profile_complete,
                "email_notifications_enabled": profile.email_notifications_enabled,
                "sms_notifications_enabled": profile.sms_notifications_enabled,
            },
            "addresses": addresses,
            "order_stats": order_stats,
            "wishlist_count": wishlist_count,
        }
