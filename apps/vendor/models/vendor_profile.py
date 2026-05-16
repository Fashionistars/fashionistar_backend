# apps/vendor/models/vendor_profile.py
"""
VendorProfile — 1:1 Profile for role='vendor' users.

Architecture decisions:
  ─ ALL reverse ORM lookups use pre-defined related_names so views/selectors
    can do: vendor.vendor_orders.filter(...) instead of N+1 CartOrder queries.
  ─ All analytics helpers are synchronous model methods (used in DRF sync views).
  ─ All async variants are classmethods here at the model/DB layer (Django 6.0
    native async ORM). Selectors delegate to these methods — ZERO sync_to_async.
  ─ CASCADE vs SET_NULL decisions:
      user → CASCADE  (profile is meaningless without a user)
      vendor FKs from other models → SET_NULL (order/review should survive vendor deletion)
  ─ Collections: M2M to catalog.Collection (admin-managed dropdown on setup page)
  ─ No raw SQL. Only ORM with select_related / prefetch_related / values().

Reverse query cheat-sheet (all use pre-defined related_names):
  user.vendor_profile                     → VendorProfile (OneToOne)
  vendor.vendor_orders.filter(...)        → CartOrder rows for this vendor
  vendor.vendor_products.filter(...)      → Product rows for this vendor
  vendor.vendor_reviews.filter(...)       → Review rows for this vendor
  vendor.vendor_coupons.filter(...)       → Coupon rows for this vendor
  vendor.vendor_wallet_transactions.filter(...) → WalletTransaction rows
  vendor.setup_state                      → VendorSetupState (OneToOne)
  vendor.vendor_payout_profile            → VendorPayoutProfile (OneToOne)
  vendor.collections.all()               → M2M Collections this vendor serves
"""

import logging
from decimal import Decimal
from datetime import timedelta
from typing import Any

from django.contrib.auth.hashers import check_password, make_password
from django.db import models, transaction
from django.db.models import Avg, Count, F, Min, Q, Sum
from django.db.models.functions import ExtractHour, ExtractMonth
from django.utils import timezone

from apps.common.models import SoftDeleteModel, TimeStampedModel
from apps.order.models import CashPaymentMode
from cloudinary.models import CloudinaryField

logger = logging.getLogger(__name__)


class VendorProfile(TimeStampedModel, SoftDeleteModel):
    """
    Extended profile for vendor-role users.

    Linked 1:1 to UnifiedUser (role='vendor').

    Reverse query cheat-sheet (usable in BOTH sync DRF and async Ninja views):
      vendor.vendor_orders.filter(...)        → CartOrder rows for this vendor
      vendor.vendor_products.filter(...)      → Product rows for this vendor
      vendor.vendor_reviews.filter(...)       → Review rows for this vendor's products
      vendor.vendor_coupons.filter(...)       → Coupon rows for this vendor
      vendor.vendor_wallet_transactions.filter(...) → WalletTransaction rows
      vendor.setup_state                      → VendorSetupState (OneToOne)
      vendor.payout_profile                   → VendorPayoutProfile (OneToOne)
      vendor.collections.all()               → M2M Collections this vendor serves
    """

    # ── Identity Link ──────────────────────────────────────────────
    user = models.OneToOneField(
        "authentication.UnifiedUser",
        on_delete=models.CASCADE,  # user deleted → profile deleted
        related_name="vendor_profile",
        limit_choices_to={"role": "vendor"},
        db_index=True,
        help_text="The vendor user this profile belongs to.",
    )

    # ── Store Identity ─────────────────────────────────────────────
    store_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Public-facing store name shown on the marketplace.",
    )
    store_slug = models.SlugField(
        max_length=160,
        unique=True,
        blank=True,
        db_index=True,
        help_text="URL-safe unique store identifier. Auto-generated from store_name.",
    )
    tagline = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(max_length=2000, blank=True, default="")

    # ── Collections (Admin-managed; vendor selects at setup) ───────
    # Admin creates Collections in catalog. Vendor picks one or more during setup.
    collections = models.ManyToManyField(
        "catalog.Collections",
        blank=True,
        related_name="vendor_collections",  # CORRECT: reflects the reverse M2M direction.
        help_text=(
            "Fashion collections this store specialises in. "
            "Displayed as a multi-select dropdown on the vendor setup page. "
            "Only admins can create Collection records."
        ),
    )

    # ── Media (Cloudinary URLs) ────────────────────────────────────
    logo_url = CloudinaryField(
        blank=True, default="", help_text="Cloudinary store logo URL."
    )
    cover_url = CloudinaryField(
        blank=True, default="", help_text="Cloudinary banner URL."
    )

    # ── Location ───────────────────────────────────────────────────
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="Nigeria")
    address = models.CharField(
        max_length=255, blank=True, default="A3 OKIGWE ROAD, UMUAHIA, ABIA STATE"
    )

    # ── Business Hours ─────────────────────────────────────────────
    opening_time = models.TimeField(blank=True, null=True)
    closing_time = models.TimeField(blank=True, null=True)
    business_hours = models.JSONField(
        default=dict,
        blank=True,
        help_text="e.g. {'Monday': '9:00-17:00', 'Tuesday': '9:00-17:00'}",
    )

    # ── Social Links ───────────────────────────────────────────────
    instagram_url = models.URLField(blank=True, default="")
    tiktok_url = models.URLField(blank=True, default="")
    twitter_url = models.URLField(blank=True, default="")
    website_url = models.URLField(blank=True, default="")
    whatsapp = models.CharField(max_length=20, blank=True, default="")
    cash_payment_mode = models.CharField(
        max_length=20,
        choices=CashPaymentMode.choices,
        default=CashPaymentMode.DISABLED,
        help_text="Storefront display preference for COD / Pay At Shop availability.",
    )

    # ── Analytics (denormalized counters — updated by EVENTS SIGNALS / TASKS AND NOT THE NORMAL DJANGO SIGNALS) ──
    total_products = models.PositiveIntegerField(default=0)
    total_sales = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0")
    )
    average_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0")
    )
    review_count = models.PositiveIntegerField(default=0)

    # ── Wallet ─────────────────────────────────────────────────────
    wallet_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )

    # ── Security ───────────────────────────────────────────────────
    transaction_password = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Bcrypt-hashed 4-digit PIN for payout confirmation.",
    )

    # ── Verification & Visibility ──────────────────────────────────
    is_verified = models.BooleanField(
        default=False,
        help_text="Manually verified by Fashionistar staff. Does NOT gate dashboard access.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name = "Vendor Profile"
        verbose_name_plural = "Vendor Profiles"
        db_table = "vendor_profile"
        indexes = [
            models.Index(fields=["user"], name="vendor_profile_user_idx"),
            models.Index(fields=["store_slug"], name="vendor_profile_slug_idx"),
            models.Index(fields=["is_verified"], name="vendor_profile_verified_idx"),
            models.Index(fields=["country"], name="vendor_profile_country_idx"),
            models.Index(fields=["is_active"], name="vendor_profile_active_idx"),
        ]

    def __str__(self) -> str:
        return f"VendorProfile({self.store_name or self.pk})"

    @property
    def vendor_product(self):
        """
        Singular alias — delegates to the reverse FK manager ``vendor_products``.

        The canonical DB related_name on Product is ``vendor_products``.
        This alias supports ``vendor.vendor_product.filter(...)`` without
        adding a second FK or DB relationship.
        """
        return self.vendor_products

    @property
    def vendor_coupons(self):
        """Compatibility alias for Coupon.vendor related_name."""
        return self.vendor_platform_wide_coupons

    @property
    def revenue_order_statuses(self) -> list[str]:
        """Statuses that represent revenue-bearing orders."""
        return [
            "payment_confirmed",
            "processing",
            "shipped",
            "out_for_delivery",
            "delivered",
            "completed",
        ]

    # NOTE: vendor_products is the real reverse manager injected by Django
    # from Product.vendor FK with related_name="vendor_products".
    # Do NOT redefine it as a property — that shadows the manager and causes
    # an infinite recursion loop. Selectors access it directly:
    #   vendor_profile.vendor_products.filter(...)

    # ── Slug auto-generation ───────────────────────────────────────

    def save(self, *args, **kwargs) -> None:
        if not self.store_slug and self.store_name:
            from django.utils.text import slugify
            import shortuuid

            base = slugify(self.store_name)
            slug = f"{base}-{shortuuid.uuid()[:4].lower()}"
            # Guarantee uniqueness
            while (
                VendorProfile.objects.filter(store_slug=slug)
                .exclude(pk=self.pk)
                .exists()
            ):
                slug = f"{base}-{shortuuid.uuid()[:4].lower()}"
            self.store_slug = slug
        super().save(*args, **kwargs)

    # ── Idempotent factory ─────────────────────────────────────────

    @classmethod
    def get_or_create_for_user(cls, user) -> "VendorProfile":
        """Return existing VendorProfile or create a blank one. Safe to call many times."""
        profile, _ = cls.objects.get_or_create(user=user)
        return profile

    @classmethod
    async def aget_or_create_for_user(cls, user) -> "VendorProfile":
        """Async: return existing VendorProfile or create a blank one."""
        profile, _ = await cls.objects.aget_or_create(user=user)
        return profile

    # ══════════════════════════════════════════════════════════════
    #  ASYNC DB-LEVEL CLASSMETHODS
    #
    #  These are the canonical database-layer query methods.
    #  Selectors in vendor_selectors.py are thin wrappers that
    #  delegate to these methods — keeping business logic at the
    #  model (DB) layer rather than the service/selector layer.
    #
    #  ALL methods are Django 6.0 native async — ZERO sync_to_async.
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def get_full_dashboard_snapshot(cls, user) -> dict[str, Any]:
        """
        Sync: return full vendor dashboard data as a plain dict.

        Single compound query: profile + setup_state + payout_profile
        via select_related. Analytics aggregates use reverse FKs.

        Args:
            user: Authenticated UnifiedUser instance (role='vendor').

        Returns:
            dict with store_name, store_slug, is_verified, total_products,
            total_sales, total_revenue, wallet_balance, average_rating,
            review_count, setup_state dict, payout_is_verified bool.
        """
        try:
            vendor = (
                cls.objects
                .select_related("user", "vendor_setup_state", "vendor_payout_profile")
                .get(user=user)
            )
            setup = getattr(vendor, "vendor_setup_state", None)
            payout = getattr(vendor, "vendor_payout_profile", None)
            return {
                "store_name": vendor.store_name,
                "store_slug": vendor.store_slug,
                "tagline": vendor.tagline,
                "is_verified": vendor.is_verified,
                "is_featured": vendor.is_featured,
                "total_products": vendor.total_products,
                "total_sales": vendor.total_sales,
                "total_revenue": float(vendor.total_revenue),
                "wallet_balance": float(vendor.wallet_balance),
                "average_rating": float(vendor.average_rating),
                "review_count": vendor.review_count,
                "city": vendor.city,
                "state": vendor.state,
                "country": vendor.country,
                "setup_state": {
                    "current_step": getattr(setup, "current_step", 1),
                    "profile_complete": getattr(setup, "profile_complete", False),
                    "bank_details": getattr(setup, "bank_details", False),
                    "id_verified": getattr(setup, "id_verified", False),
                    "first_product": getattr(setup, "first_product", False),
                    "onboarding_done": getattr(setup, "onboarding_done", False),
                    "completion_percentage": getattr(setup, "completion_percentage", 0),
                } if setup else {},
                "payout_is_verified": getattr(payout, "is_verified", False),
            }
        except cls.DoesNotExist:
            return {}
        except Exception as exc:
            logger.error("get_full_dashboard_snapshot user=%s: %s", user, exc)
            return {}

    @classmethod
    async def aget_full_dashboard_snapshot(cls, user) -> dict[str, Any]:
        """
        Async: return full vendor dashboard data as a plain dict.

        Uses Django 6.0 native aget() with select_related.
        Delegates reverse-FK aggregates to individual async calls.

        Args:
            user: Authenticated UnifiedUser instance (role='vendor').

        Returns:
            dict matching get_full_dashboard_snapshot().
        """
        try:
            vendor = await (
                cls.objects
                .select_related("user", "vendor_setup_state", "vendor_payout_profile")
                .aget(user=user)
            )
            setup = getattr(vendor, "vendor_setup_state", None)
            payout = getattr(vendor, "vendor_payout_profile", None)
            return {
                "store_name": vendor.store_name,
                "store_slug": vendor.store_slug,
                "tagline": vendor.tagline,
                "is_verified": vendor.is_verified,
                "is_featured": vendor.is_featured,
                "total_products": vendor.total_products,
                "total_sales": vendor.total_sales,
                "total_revenue": float(vendor.total_revenue),
                "wallet_balance": float(vendor.wallet_balance),
                "average_rating": float(vendor.average_rating),
                "review_count": vendor.review_count,
                "city": vendor.city,
                "state": vendor.state,
                "country": vendor.country,
                "setup_state": {
                    "current_step": getattr(setup, "current_step", 1),
                    "profile_complete": getattr(setup, "profile_complete", False),
                    "bank_details": getattr(setup, "bank_details", False),
                    "id_verified": getattr(setup, "id_verified", False),
                    "first_product": getattr(setup, "first_product", False),
                    "onboarding_done": getattr(setup, "onboarding_done", False),
                    "completion_percentage": getattr(setup, "completion_percentage", 0),
                } if setup else {},
                "payout_is_verified": getattr(payout, "is_verified", False),
            }
        except cls.DoesNotExist:
            return {}
        except Exception as exc:
            logger.error("aget_full_dashboard_snapshot user=%s: %s", user, exc)
            return {}

    @classmethod
    def get_order_stats_from_db(cls, vendor) -> dict[str, Any]:
        """
        Sync: aggregate order stats for a vendor (total count + total revenue).

        Uses reverse FK: vendor.vendor_orders.

        Args:
            vendor: VendorProfile instance.

        Returns:
            dict with total_orders, total_revenue, pending_count, active_count.
        """
        try:
            agg = vendor.vendor_orders.aggregate(
                total_orders=Count("id"),
                total_revenue=Sum("total_amount"),
            )
            pending = vendor.vendor_orders.filter(status="pending_payment").count()
            active = vendor.vendor_orders.filter(
                status__in=["processing", "shipped", "out_for_delivery"]
            ).count()
            return {
                "total_orders": agg["total_orders"] or 0,
                "total_revenue": float(agg["total_revenue"] or 0),
                "pending_count": pending,
                "active_count": active,
            }
        except Exception as exc:
            logger.error("get_order_stats_from_db vendor=%s: %s", vendor.pk, exc)
            return {"total_orders": 0, "total_revenue": 0.0, "pending_count": 0, "active_count": 0}

    @classmethod
    async def aget_order_stats_from_db(cls, vendor) -> dict[str, Any]:
        """
        Async: aggregate order stats for a vendor.

        Uses Django 6.0 aaggregate() + acount() native async ORM.
        ZERO sync_to_async.

        Args:
            vendor: VendorProfile instance.

        Returns:
            dict with total_orders, total_revenue, pending_count, active_count.
        """
        try:
            agg = await vendor.vendor_orders.aaggregate(
                total_orders=Count("id"),
                total_revenue=Sum("total_amount"),
            )
            pending = await vendor.vendor_orders.filter(status="pending_payment").acount()
            active = await vendor.vendor_orders.filter(
                status__in=["processing", "shipped", "out_for_delivery"]
            ).acount()
            return {
                "total_orders": agg["total_orders"] or 0,
                "total_revenue": float(agg["total_revenue"] or 0),
                "pending_count": pending,
                "active_count": active,
            }
        except Exception as exc:
            logger.error("aget_order_stats_from_db vendor=%s: %s", vendor.pk, exc)
            return {"total_orders": 0, "total_revenue": 0.0, "pending_count": 0, "active_count": 0}

    @classmethod
    def get_product_summary_from_db(cls, vendor, limit: int = 10) -> list[dict]:
        """
        Sync: top N products by creation date for the vendor dashboard.

        Uses reverse FK: vendor.vendor_products.

        Args:
            vendor: VendorProfile instance.
            limit: Max rows to return (default 10).

        Returns:
            list[dict] with id, title, price, stock_qty, status.
        """
        try:
            return list(
                vendor.vendor_products
                .order_by("-created_at")
                .values("id", "title", "price", "stock_qty", "status")[:limit]
            )
        except Exception as exc:
            logger.error("get_product_summary_from_db vendor=%s: %s", vendor.pk, exc)
            return []

    @classmethod
    async def aget_product_summary_from_db(cls, vendor, limit: int = 10) -> list[dict]:
        """
        Async: top N products by creation date for the vendor dashboard.

        Uses async iteration over the reverse FK queryset.
        ZERO sync_to_async.

        Args:
            vendor: VendorProfile instance.
            limit: Max rows to return (default 10).

        Returns:
            list[dict] with id, title, price, stock_qty, status.
        """
        try:
            qs = (
                vendor.vendor_products
                .order_by("-created_at")
                .values("id", "title", "price", "stock_qty", "status")[:limit]
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_product_summary_from_db vendor=%s: %s", vendor.pk, exc)
            return []

    @classmethod
    def get_wallet_balance_from_db(cls, vendor) -> float:
        """
        Sync: compute live wallet balance from WalletTransaction sum.

        Uses reverse FK: vendor.vendor_wallet_transactions.

        Args:
            vendor: VendorProfile instance.

        Returns:
            float wallet balance (sum of all transaction amounts).
        """
        try:
            from apps.wallet.models import Wallet

            wallet = (
                Wallet.objects.filter(
                    user_id=vendor.user_id,
                    owner_type="vendor",
                    is_default=True,
                )
                .only("balance")
                .first()
            )
            return float(getattr(wallet, "balance", 0) or 0)
        except Exception as exc:
            logger.error("get_wallet_balance_from_db vendor=%s: %s", vendor.pk, exc)
            return 0.0

    @classmethod
    async def aget_wallet_balance_from_db(cls, vendor) -> float:
        """
        Async: compute live wallet balance from WalletTransaction sum.

        Uses aaggregate(Sum) — Django 6.0 native async ORM.
        ZERO sync_to_async.

        Args:
            vendor: VendorProfile instance.

        Returns:
            float wallet balance.
        """
        try:
            from apps.wallet.models import Wallet

            wallet = await (
                Wallet.objects.filter(
                    user_id=vendor.user_id,
                    owner_type="vendor",
                    is_default=True,
                )
                .only("balance")
                .afirst()
            )
            return float(getattr(wallet, "balance", 0) or 0)
        except Exception as exc:
            logger.error("aget_wallet_balance_from_db vendor=%s: %s", vendor.pk, exc)
            return 0.0

    @classmethod
    async def aget_top_selling_products_from_db(
        cls, vendor, limit: int = 5
    ) -> list[dict]:
        """
        Async: top products by quantity sold.

        Traversal: vendor_products → cart_order_product_snapshots.
        Uses annotate(Sum) + async iteration — Django 6.0 native.
        ZERO sync_to_async.

        Args:
            vendor: VendorProfile instance.
            limit: Max rows to return (default 5).

        Returns:
            list[dict] with id, title, price, stock_qty, total_qty.
        """
        try:
            qs = (
                vendor.vendor_products
                .annotate(total_qty=Sum("cart_order_product_snapshots__quantity"))
                .order_by("-total_qty")
                .values("id", "title", "price", "stock_qty", "total_qty")[:limit]
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_top_selling_products_from_db vendor=%s: %s", vendor.pk, exc)
            return []

    @classmethod
    async def aget_coupon_stats_from_db(cls, vendor) -> dict[str, int]:
        """
        Async: return active and inactive coupon counts.

        Uses vendor.vendor_coupons reverse FK + acount().
        ZERO sync_to_async.

        Args:
            vendor: VendorProfile instance.

        Returns:
            dict with active (int) and inactive (int).
        """
        try:
            active = await vendor.vendor_coupons.filter(active=True).acount()
            inactive = await vendor.vendor_coupons.filter(active=False).acount()
            return {"active": active, "inactive": inactive}
        except Exception as exc:
            logger.error("aget_coupon_stats_from_db vendor=%s: %s", vendor.pk, exc)
            return {"active": 0, "inactive": 0}

    @classmethod
    async def aget_recent_orders_from_db(
        cls, vendor, limit: int = 10
    ) -> list[dict]:
        """
        Async: most recent N orders for this vendor as list[dict].

        Traversal: vendor.vendor_orders (reverse FK on CartOrder).
        Uses async iteration over .values() — ZERO sync_to_async.

        Args:
            vendor: VendorProfile instance.
            limit: Max rows to return (default 10).

        Returns:
            list[dict] with id, total_amount, status, created_at, fulfillment_type.
        """
        try:
            qs = (
                vendor.vendor_orders
                .order_by("-created_at")
                .values("id", "total_amount", "status", "created_at", "fulfillment_type")[:limit]
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_recent_orders_from_db vendor=%s: %s", vendor.pk, exc)
            return []

    # ── Transaction password helpers ───────────────────────────────

    def set_transaction_password(self, raw_pin: str) -> None:
        """Hash and store a 4-digit payout PIN."""
        self.transaction_password = make_password(raw_pin)
        self.save(update_fields=["transaction_password", "updated_at"])

    def check_transaction_password(self, raw_pin: str) -> bool:
        """Verify a plain PIN against the stored bcrypt hash."""
        return check_password(raw_pin, self.transaction_password)

    # ══════════════════════════════════════════════════════════════
    #  ANALYTICS METHODS — all use reverse related_names to avoid N+1.
    #
    #  These methods are called in SYNCHRONOUS DRF views.
    #  For the async Ninja dashboard, use the async selector functions
    #  in apps/vendor/selectors/vendor_selectors.py instead.
    # ══════════════════════════════════════════════════════════════

    def get_average_rating(self) -> float:
        """
        Average rating across all vendor products.
        Uses: vendor_products → review_product (reverse from Review model).
        """
        try:
            return (
                self.vendor_products.aggregate(avg=Avg("reviews__rating")).get(
                    "avg"
                )
                or 0.0
            )
        except Exception as exc:
            logger.error("get_average_rating vendor=%s: %s", self.pk, exc)
            return 0.0

    def get_wallet_balance(self) -> Decimal:
        """
        Live wallet balance from WalletTransaction.
        Uses: vendor_wallet_transactions reverse FK.
        """
        try:
            from apps.wallet.models import Wallet

            wallet = (
                Wallet.objects.filter(
                    user_id=self.user_id,
                    owner_type="vendor",
                    is_default=True,
                )
                .only("balance")
                .first()
            )
            return getattr(wallet, "balance", Decimal("0")) or Decimal("0")
        except Exception as exc:
            logger.error("get_wallet_balance vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    def get_pending_payouts(self) -> Decimal:
        """
        Total value of pending (unpaid) orders.
        Uses: vendor_orders reverse FK → CartOrder.
        """
        try:
            result = (
                self.vendor_orders.filter(status="pending_payment")
                .aggregate(total=Sum("total_amount"))
                .get("total")
            )
            return result or Decimal("0")
        except Exception as exc:
            logger.error("get_pending_payouts vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    def get_order_status_counts(self):
        """
        Count orders grouped by payment_status.
        Uses: vendor_orders reverse FK.
        """
        try:
            return self.vendor_orders.values("status").annotate(
                count=Count("id")
            )
        except Exception as exc:
            logger.error("get_order_status_counts vendor=%s: %s", self.pk, exc)
            return []

    def get_top_selling_products(self, limit: int = 5):
        """
        Top products by quantity sold.
        Uses: vendor_products → order_item_product (reverse from CartOrderItem).
        """
        try:
            return self.vendor_products.annotate(
                total_qty=Sum("cart_order_product_snapshots__quantity")
            ).order_by("-total_qty")[:limit]
        except Exception as exc:
            logger.error("get_top_selling_products vendor=%s: %s", self.pk, exc)
            return []

    def get_revenue_trends(self, months: int = 6):
        """
        Monthly revenue over the last N months.
        Uses: vendor_orders reverse FK.
        """
        try:
            cutoff = timezone.now() - timedelta(days=months * 30)
            return (
                self.vendor_orders.filter(
                    status__in=self.revenue_order_statuses,
                    created_at__gte=cutoff,
                )
                .annotate(month=ExtractMonth("created_at"))
                .values("month")
                .annotate(total_revenue=Sum("total_amount"))
                .order_by("month")
            )
        except Exception as exc:
            logger.error("get_revenue_trends vendor=%s: %s", self.pk, exc)
            return []

    def get_customer_behavior(self):
        """
        Order count grouped by hour of day (paid orders).
        Uses: vendor_orders reverse FK.
        """
        try:
            return (
                self.vendor_orders.filter(status__in=self.revenue_order_statuses)
                .annotate(hour=ExtractHour("created_at"))
                .values("hour")
                .annotate(order_count=Count("id"))
                .order_by("hour")
            )
        except Exception as exc:
            logger.error("get_customer_behavior vendor=%s: %s", self.pk, exc)
            return []

    def get_low_stock_alerts(self, threshold: int = 5):
        """
        Products with stock_qty below threshold.
        Uses: vendor_products reverse FK.
        """
        try:
            return self.vendor_products.filter(stock_qty__lt=threshold).values(
                "title", "stock_qty"
            )
        except Exception as exc:
            logger.error("get_low_stock_alerts vendor=%s: %s", self.pk, exc)
            return []

    def get_review_count(self) -> int:
        """
        Total number of reviews on all vendor products.
        Uses: vendor_products → review_product.
        """
        try:
            return (
                self.vendor_products.aggregate(total=Count("reviews")).get(
                    "total"
                )
                or 0
            )
        except Exception as exc:
            logger.error("get_review_count vendor=%s: %s", self.pk, exc)
            return 0

    def get_average_review_rating(self) -> float:
        """Alias for get_average_rating — kept for API backward-compat."""
        return self.get_average_rating()

    def get_coupon_data(self):
        """
        Coupon codes + discounts for this vendor.
        Uses: vendor_coupons reverse FK.
        """
        try:
            return self.vendor_coupons.values("code", "discount_value", "valid_from")
        except Exception as exc:
            logger.error("get_coupon_data vendor=%s: %s", self.pk, exc)
            return []

    def get_active_coupons(self) -> int:
        """Count of active coupons. Uses: vendor_coupons reverse FK."""
        try:
            return self.vendor_coupons.filter(active=True).count()
        except Exception as exc:
            logger.error("get_active_coupons vendor=%s: %s", self.pk, exc)
            return 0

    def get_inactive_coupons(self) -> int:
        """Count of inactive coupons. Uses: vendor_coupons reverse FK."""
        try:
            return self.vendor_coupons.filter(active=False).count()
        except Exception as exc:
            logger.error("get_inactive_coupons vendor=%s: %s", self.pk, exc)
            return 0

    def get_abandoned_carts(self):
        """
        Pending orders (abandoned carts).
        Uses: vendor_orders reverse FK.
        """
        try:
            return self.vendor_orders.filter(status="pending_payment").values(
                "user__email", "total_amount"
            )
        except Exception as exc:
            logger.error("get_abandoned_carts vendor=%s: %s", self.pk, exc)
            return []

    def get_total_customers(self) -> int:
        """
        Count of unique buyers who have ordered from this vendor.
        Uses: vendor_orders reverse FK.
        """
        try:
            return self.vendor_orders.exclude(user__isnull=True).values("user").distinct().count()
        except Exception as exc:
            logger.error("get_total_customers vendor=%s: %s", self.pk, exc)
            return 0

    def get_todays_sales(self) -> Decimal:
        """Total paid sales for today. Uses: vendor_orders."""
        try:
            today = timezone.now().date()
            return self.vendor_orders.filter(
                status__in=self.revenue_order_statuses, created_at__date=today
            ).aggregate(total=Sum("total_amount")).get("total") or Decimal("0")
        except Exception as exc:
            logger.error("get_todays_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    def get_this_month_sales(self) -> Decimal:
        """Total paid sales for the current calendar month."""
        try:
            now = timezone.now()
            return self.vendor_orders.filter(
                status__in=self.revenue_order_statuses,
                created_at__month=now.month,
                created_at__year=now.year,
            ).aggregate(total=Sum("total_amount")).get("total") or Decimal("0")
        except Exception as exc:
            logger.error("get_this_month_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    def get_year_to_date_sales(self) -> Decimal:
        """Total paid sales for the current year."""
        try:
            now = timezone.now()
            return self.vendor_orders.filter(
                status__in=self.revenue_order_statuses, created_at__year=now.year
            ).aggregate(total=Sum("total_amount")).get("total") or Decimal("0")
        except Exception as exc:
            logger.error("get_year_to_date_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    def calculate_average_order_value(self) -> float:
        """Avg order value for fulfilled orders."""
        try:
            return (
                self.vendor_orders.filter(status__in=["delivered", "completed"])
                .aggregate(avg=Avg("total_amount"))
                .get("avg")
                or 0.0
            )
        except Exception as exc:
            logger.error("calculate_average_order_value vendor=%s: %s", self.pk, exc)
            return 0.0

    def calculate_total_sales(self) -> Decimal:
        """Total revenue from paid orders."""
        try:
            return self.vendor_orders.filter(status__in=self.revenue_order_statuses).aggregate(
                total=Sum("total_amount")
            ).get("total") or Decimal("0")
        except Exception as exc:
            logger.error("calculate_total_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    def get_top_performing_categories(self, limit: int = 5):
        """
        Top product categories by total revenue.
        Traversal: vendor_products → categories__name / cart_order_product_snapshots.
        """
        try:
            return list(
                self.vendor_products.values("categories__name")
                .annotate(sales=Sum("cart_order_product_snapshots__line_total"))
                .order_by("-sales")[:limit]
            )
        except Exception as exc:
            logger.error("get_top_performing_categories vendor=%s: %s", self.pk, exc)
            return []

    def get_payment_method_distribution(self):
        """
        Revenue split by order status, returned as percentage list.
        Uses: vendor_orders reverse FK.
        """
        try:
            rows = self.vendor_orders.values("status").annotate(
                total=Sum("total_amount")
            )
            total_revenue = sum(r["total"] or 0 for r in rows)
            if not total_revenue:
                return []
            return [
                {
                    "payment_method": r["status"],
                    "percentage": round(
                        float(r["total"] or 0) / float(total_revenue) * 100, 2
                    ),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("get_payment_method_distribution vendor=%s: %s", self.pk, exc)
            return []

    def get_new_customers_this_month(self) -> int:
        """
        Customers who placed their FIRST-EVER order this month with this vendor.
        Uses a subquery approach to avoid the N+1 loop from the old model.
        Uses: vendor_orders reverse FK.
        """
        try:
            now = timezone.now()
            return (
                self.vendor_orders.exclude(user__isnull=True)
                .values("user_id")
                .annotate(first_order_at=Min("created_at"))
                .filter(
                    first_order_at__month=now.month,
                    first_order_at__year=now.year,
                )
                .count()
            )
        except Exception as exc:
            logger.error("get_new_customers_this_month vendor=%s: %s", self.pk, exc)
            return 0

    # ══════════════════════════════════════════════════════════════
    #  ASYNC ANALYTICS METHODS
    # ══════════════════════════════════════════════════════════════

    async def aget_average_rating(self) -> float:
        try:
            result = await self.vendor_products.aaggregate(avg=Avg("reviews__rating"))
            return result.get("avg") or 0.0
        except Exception as exc:
            logger.error("aget_average_rating vendor=%s: %s", self.pk, exc)
            return 0.0

    async def aget_wallet_balance(self) -> Decimal:
        try:
            from apps.wallet.models import Wallet
            wallet = await (
                Wallet.objects.filter(
                    user_id=self.user_id,
                    owner_type="vendor",
                    is_default=True,
                )
                .only("balance")
                .afirst()
            )
            return getattr(wallet, "balance", Decimal("0")) or Decimal("0")
        except Exception as exc:
            logger.error("aget_wallet_balance vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    async def aget_pending_payouts(self) -> Decimal:
        try:
            result = await (
                self.vendor_orders.filter(status="pending_payment")
                .aaggregate(total=Sum("total_amount"))
            )
            return result.get("total") or Decimal("0")
        except Exception as exc:
            logger.error("aget_pending_payouts vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    async def aget_order_status_counts(self):
        try:
            qs = self.vendor_orders.values("status").annotate(count=Count("id"))
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_order_status_counts vendor=%s: %s", self.pk, exc)
            return []

    async def aget_top_selling_products(self, limit: int = 5):
        try:
            qs = self.vendor_products.annotate(
                total_qty=Sum("cart_order_product_snapshots__quantity")
            ).order_by("-total_qty")[:limit]
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_top_selling_products vendor=%s: %s", self.pk, exc)
            return []

    async def aget_revenue_trends(self, months: int = 6):
        try:
            cutoff = timezone.now() - timedelta(days=months * 30)
            qs = (
                self.vendor_orders.filter(
                    status__in=self.revenue_order_statuses,
                    created_at__gte=cutoff,
                )
                .annotate(month=ExtractMonth("created_at"))
                .values("month")
                .annotate(total_revenue=Sum("total_amount"))
                .order_by("month")
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_revenue_trends vendor=%s: %s", self.pk, exc)
            return []

    async def aget_customer_behavior(self):
        try:
            qs = (
                self.vendor_orders.filter(status__in=self.revenue_order_statuses)
                .annotate(hour=ExtractHour("created_at"))
                .values("hour")
                .annotate(order_count=Count("id"))
                .order_by("hour")
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_customer_behavior vendor=%s: %s", self.pk, exc)
            return []

    async def aget_low_stock_alerts(self, threshold: int = 5):
        try:
            qs = self.vendor_products.filter(stock_qty__lt=threshold).values(
                "title", "stock_qty"
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_low_stock_alerts vendor=%s: %s", self.pk, exc)
            return []

    async def aget_review_count(self) -> int:
        try:
            result = await self.vendor_products.aaggregate(total=Count("reviews"))
            return result.get("total") or 0
        except Exception as exc:
            logger.error("aget_review_count vendor=%s: %s", self.pk, exc)
            return 0

    async def aget_average_review_rating(self) -> float:
        return await self.aget_average_rating()

    async def aget_coupon_data(self):
        try:
            qs = self.vendor_coupons.values("code", "discount_value", "valid_from")
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_coupon_data vendor=%s: %s", self.pk, exc)
            return []

    async def aget_active_coupons(self) -> int:
        try:
            return await self.vendor_coupons.filter(active=True).acount()
        except Exception as exc:
            logger.error("aget_active_coupons vendor=%s: %s", self.pk, exc)
            return 0

    async def aget_inactive_coupons(self) -> int:
        try:
            return await self.vendor_coupons.filter(active=False).acount()
        except Exception as exc:
            logger.error("aget_inactive_coupons vendor=%s: %s", self.pk, exc)
            return 0

    async def aget_abandoned_carts(self):
        try:
            qs = self.vendor_orders.filter(status="pending_payment").values(
                "user__email", "total_amount"
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_abandoned_carts vendor=%s: %s", self.pk, exc)
            return []

    async def aget_total_customers(self) -> int:
        try:
            return await self.vendor_orders.exclude(user__isnull=True).values("user").distinct().acount()
        except Exception as exc:
            logger.error("aget_total_customers vendor=%s: %s", self.pk, exc)
            return 0

    async def aget_todays_sales(self) -> Decimal:
        try:
            today = timezone.now().date()
            result = await self.vendor_orders.filter(
                status__in=self.revenue_order_statuses, created_at__date=today
            ).aaggregate(total=Sum("total_amount"))
            return result.get("total") or Decimal("0")
        except Exception as exc:
            logger.error("aget_todays_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    async def aget_this_month_sales(self) -> Decimal:
        try:
            now = timezone.now()
            result = await self.vendor_orders.filter(
                status__in=self.revenue_order_statuses,
                created_at__month=now.month,
                created_at__year=now.year,
            ).aaggregate(total=Sum("total_amount"))
            return result.get("total") or Decimal("0")
        except Exception as exc:
            logger.error("aget_this_month_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    async def aget_year_to_date_sales(self) -> Decimal:
        try:
            now = timezone.now()
            result = await self.vendor_orders.filter(
                status__in=self.revenue_order_statuses, created_at__year=now.year
            ).aaggregate(total=Sum("total_amount"))
            return result.get("total") or Decimal("0")
        except Exception as exc:
            logger.error("aget_year_to_date_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    async def acalculate_average_order_value(self) -> float:
        try:
            result = await self.vendor_orders.filter(status__in=["delivered", "completed"]).aaggregate(avg=Avg("total_amount"))
            return result.get("avg") or 0.0
        except Exception as exc:
            logger.error("acalculate_average_order_value vendor=%s: %s", self.pk, exc)
            return 0.0

    async def acalculate_total_sales(self) -> Decimal:
        try:
            result = await self.vendor_orders.filter(status__in=self.revenue_order_statuses).aaggregate(total=Sum("total_amount"))
            return result.get("total") or Decimal("0")
        except Exception as exc:
            logger.error("acalculate_total_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    async def aget_top_performing_categories(self, limit: int = 5):
        try:
            qs = (
                self.vendor_products.values("categories__name")
                .annotate(sales=Sum("cart_order_product_snapshots__line_total"))
                .order_by("-sales")[:limit]
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_top_performing_categories vendor=%s: %s", self.pk, exc)
            return []

    async def aget_payment_method_distribution(self):
        try:
            qs = self.vendor_orders.values("status").annotate(total=Sum("total_amount"))
            rows = [row async for row in qs]
            total_revenue = sum(r["total"] or 0 for r in rows)
            if not total_revenue:
                return []
            return [
                {
                    "payment_method": r["status"],
                    "percentage": round(float(r["total"] or 0) / float(total_revenue) * 100, 2),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("aget_payment_method_distribution vendor=%s: %s", self.pk, exc)
            return []

    async def aget_new_customers_this_month(self) -> int:
        try:
            now = timezone.now()
            return await (
                self.vendor_orders.exclude(user__isnull=True)
                .values("user_id")
                .annotate(first_order_at=Min("created_at"))
                .filter(
                    first_order_at__month=now.month,
                    first_order_at__year=now.year,
                )
                .acount()
            )
        except Exception as exc:
            logger.error("aget_new_customers_this_month vendor=%s: %s", self.pk, exc)
            return 0
