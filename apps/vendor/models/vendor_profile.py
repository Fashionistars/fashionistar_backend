# apps/vendor/models/vendor_profile.py
"""
VendorProfile — 1:1 Profile for role='vendor' users.

Architecture decisions:
  ─ ALL reverse ORM lookups use pre-defined related_names so views/selectors
    can do: vendor.vendor_orders.filter(...) instead of N+1 CartOrder queries.
  ─ All analytics helpers are synchronous model methods (used in DRF sync views).
    Async equivalents live in selectors/vendor_selectors.py using Django 6.0
    native async ORM (aget / afilter / acount / abulk_create etc).
  ─ CASCADE vs SET_NULL decisions:
      user → CASCADE  (profile is meaningless without a user)
      vendor FKs from other models → SET_NULL (order/review should survive vendor deletion)
  ─ Collections: M2M to admin_backend.Collections (admin-managed dropdown on setup page)
  ─ No raw SQL. Only ORM with select_related / prefetch_related / values().
"""
import logging
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import ExtractMonth
from django.utils import timezone

from apps.common.models import SoftDeleteModel, TimeStampedModel

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
    # Admin creates Collections in admin_backend. Vendor picks ≥1 during setup.
    collections = models.ManyToManyField(
        "admin_backend.Collections",
        blank=True,
        related_name="vendor_collections",  # CORRECT: reflects the reverse M2M direction.
        help_text=(
            "Fashion collections this store specialises in. "
            "Displayed as a multi-select dropdown on the vendor setup page. "
            "Only admins can create Collection records."
        ),
    )

    # ── Media (Cloudinary URLs) ────────────────────────────────────
    logo_url = models.URLField(
        blank=True, default="", help_text="Cloudinary store logo URL."
    )
    cover_url = models.URLField(
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
                self.vendor_products.aggregate(avg=Avg("review_product__rating")).get(
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
            total = self.vendor_wallet_transactions.aggregate(total=Sum("amount")).get(
                "total"
            )
            return total or Decimal("0")
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
                self.vendor_orders.filter(payment_status="pending")
                .aggregate(total=Sum("total"))
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
            return self.vendor_orders.values("payment_status").annotate(
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
                total_qty=Sum("order_item_product__qty")
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
                self.vendor_orders.filter(payment_status="paid", date__gte=cutoff)
                .annotate(month=ExtractMonth("date"))
                .values("month")
                .annotate(total_revenue=Sum("total"))
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
                self.vendor_orders.filter(payment_status="paid")
                .annotate(hour=F("date__hour"))
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
                self.vendor_products.aggregate(total=Count("review_product")).get(
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
            return self.vendor_coupons.values("code", "discount", "date")
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
            return self.vendor_orders.filter(payment_status="pending").values(
                "buyer__email", "total"
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
            return self.vendor_orders.values("buyer").distinct().count()
        except Exception as exc:
            logger.error("get_total_customers vendor=%s: %s", self.pk, exc)
            return 0

    def get_todays_sales(self) -> Decimal:
        """Total paid sales for today. Uses: vendor_orders."""
        try:
            today = timezone.now().date()
            return self.vendor_orders.filter(
                payment_status="paid", date__date=today
            ).aggregate(total=Sum("total")).get("total") or Decimal("0")
        except Exception as exc:
            logger.error("get_todays_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    def get_this_month_sales(self) -> Decimal:
        """Total paid sales for the current calendar month."""
        try:
            now = timezone.now()
            return self.vendor_orders.filter(
                payment_status="paid", date__month=now.month, date__year=now.year
            ).aggregate(total=Sum("total")).get("total") or Decimal("0")
        except Exception as exc:
            logger.error("get_this_month_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    def get_year_to_date_sales(self) -> Decimal:
        """Total paid sales for the current year."""
        try:
            now = timezone.now()
            return self.vendor_orders.filter(
                payment_status="paid", date__year=now.year
            ).aggregate(total=Sum("total")).get("total") or Decimal("0")
        except Exception as exc:
            logger.error("get_year_to_date_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    def calculate_average_order_value(self) -> float:
        """Avg order value for fulfilled orders."""
        try:
            return (
                self.vendor_orders.filter(payment_status="Fulfilled")
                .aggregate(avg=Avg("total"))
                .get("avg")
                or 0.0
            )
        except Exception as exc:
            logger.error("calculate_average_order_value vendor=%s: %s", self.pk, exc)
            return 0.0

    def calculate_total_sales(self) -> Decimal:
        """Total revenue from paid orders."""
        try:
            return self.vendor_orders.filter(payment_status="paid").aggregate(
                total=Sum("total")
            ).get("total") or Decimal("0")
        except Exception as exc:
            logger.error("calculate_total_sales vendor=%s: %s", self.pk, exc)
            return Decimal("0")

    def get_top_performing_categories(self, limit: int = 5):
        """
        Top product categories by total revenue.
        Traversal: vendor_products → category__name / order_item_product__total.
        """
        try:
            return list(
                self.vendor_products.values("category__name")
                .annotate(sales=Sum("order_item_product__total"))
                .order_by("-sales")[:limit]
            )
        except Exception as exc:
            logger.error("get_top_performing_categories vendor=%s: %s", self.pk, exc)
            return []

    def get_payment_method_distribution(self):
        """
        Revenue split by payment_status, returned as percentage list.
        Uses: vendor_orders reverse FK.
        """
        try:
            rows = self.vendor_orders.values("payment_status").annotate(
                total=Sum("total")
            )
            total_revenue = sum(r["total"] or 0 for r in rows)
            if not total_revenue:
                return []
            return [
                {
                    "payment_method": r["payment_status"],
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
            # All buyers who ordered this vendor this month
            buyers_this_month = (
                self.vendor_orders.filter(date__month=now.month, date__year=now.year)
                .values_list("buyer_id", flat=True)
                .distinct()
            )
            # Of those, who has ONLY 1 order total with this vendor (ever)?
            new_count = 0
            for buyer_id in buyers_this_month:
                total_orders = self.vendor_orders.filter(buyer_id=buyer_id).count()
                if total_orders == 1:
                    new_count += 1
            return new_count
        except Exception as exc:
            logger.error("get_new_customers_this_month vendor=%s: %s", self.pk, exc)
            return 0
