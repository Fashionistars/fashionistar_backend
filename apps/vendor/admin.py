# apps/vendor/admin.py
"""
Vendor Domain Admin — Production-Grade Django Admin.

Features:
  ─ VendorProfileAdmin: full-featured admin with computed columns,
    custom list filters, bulk verify/suspend actions, inline editors
    for SetupState and PayoutProfile.
  ─ Inline admins: VendorSetupStateInline, VendorPayoutProfileInline.
  ─ SimpleListFilter for onboarding completion status.
  ─ Custom admin actions: verify, suspend, feature/unfeature vendors.
  ─ select_related + prefetch_related used on all QuerySets.
  ─ No raw SQL — all ORM annotations.
  ─ date_hierarchy on created_at for time-based drill-down.
"""
import logging

from django.contrib import admin, messages
from django.db.models import Avg, Count, Sum, QuerySet
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.vendor.models import VendorPayoutProfile, VendorProfile, VendorSetupState

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
#  Custom List Filters
# ══════════════════════════════════════════════════════════════════


class OnboardingStatusFilter(admin.SimpleListFilter):
    """
    Filter vendors by onboarding completion status.
    Reads from the VendorSetupState.onboarding_done field via reverse FK.
    """
    title  = _("Onboarding Status")
    parameter_name = "onboarding_status"

    def lookups(self, request, model_admin):
        return [
            ("complete",   _("✅ Complete (Store Live)")),
            ("incomplete", _("⏳ Incomplete (Still Onboarding)")),
        ]

    def queryset(self, request, queryset: QuerySet) -> QuerySet:
        if self.value() == "complete":
            return queryset.filter(setup_state__onboarding_done=True)
        if self.value() == "incomplete":
            return queryset.filter(setup_state__onboarding_done=False)
        return queryset


class HasPayoutProfileFilter(admin.SimpleListFilter):
    """Filter vendors who have OR have not added their payout profile."""
    title  = _("Payout Profile")
    parameter_name = "has_payout"

    def lookups(self, request, model_admin):
        return [
            ("yes", _("✅ Has Payout Profile")),
            ("no",  _("❌ No Payout Profile Yet")),
        ]

    def queryset(self, request, queryset: QuerySet) -> QuerySet:
        if self.value() == "yes":
            return queryset.filter(payout_profile__isnull=False)
        if self.value() == "no":
            return queryset.filter(payout_profile__isnull=True)
        return queryset


class HasProductsFilter(admin.SimpleListFilter):
    """Filter by whether the vendor has listed at least one product."""
    title  = _("Has Products")
    parameter_name = "has_products"

    def lookups(self, request, model_admin):
        return [
            ("yes", _("✅ Has Products")),
            ("no",  _("❌ No Products Yet")),
        ]

    def queryset(self, request, queryset: QuerySet) -> QuerySet:
        if self.value() == "yes":
            return queryset.filter(total_products__gt=0)
        if self.value() == "no":
            return queryset.filter(total_products=0)
        return queryset


# ══════════════════════════════════════════════════════════════════
#  Inline Admins
# ══════════════════════════════════════════════════════════════════


class VendorSetupStateInline(admin.StackedInline):
    """
    Show onboarding status inline within VendorProfile admin.
    Read-only — staff uses this to view progress, not edit it.
    (Changes to steps are triggered through business logic, not admin.)
    """
    model          = VendorSetupState
    can_delete     = False
    max_num        = 1
    extra          = 0
    verbose_name   = "Onboarding Setup State"
    fields         = [
        "current_step",
        "profile_complete",
        "bank_details",
        "first_product",
        "onboarding_done",
        "id_verified",   # future KYC — shown but informational only
    ]
    readonly_fields = [
        "current_step",
        "profile_complete",
        "bank_details",
        "first_product",
        "onboarding_done",
    ]


class VendorPayoutProfileInline(admin.StackedInline):
    """
    Show payout/bank details inline within VendorProfile admin.
    Encrypted account number never exposed — only last 4 digits shown.
    """
    model          = VendorPayoutProfile
    can_delete     = False
    max_num        = 1
    extra          = 0
    verbose_name   = "Bank / Payout Profile"
    fields         = [
        "bank_name",
        "bank_code",
        "account_name",
        "account_last4",
        "paystack_recipient_code",
        "is_verified",
    ]
    readonly_fields = ["account_last4", "account_number_enc"]


# ══════════════════════════════════════════════════════════════════
#  VendorProfile Admin
# ══════════════════════════════════════════════════════════════════


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    """
    Full-featured admin for VendorProfile.

    Key capabilities:
      ─ Computed columns: onboarding_status_badge, revenue_display.
      ─ Bulk admin actions: verify, suspend, feature/unfeature.
      ─ Inline editors: SetupState + PayoutProfile.
      ─ Advanced filters: OnboardingStatusFilter, HasPayoutProfileFilter.
      ─ select_related + prefetch_related on all list views.
      ─ date_hierarchy for time-based drill-down.
      ─ Raw ID fields for FKs that can have large datasets.
    """

    # ── Display ────────────────────────────────────────────────────
    list_display = [
        "store_name",
        "user_email",
        "country",
        "onboarding_status_badge",
        "is_verified",
        "is_active",
        "is_featured",
        "total_products",
        "total_sales",
        "revenue_display",
        "created_at",
    ]
    list_display_links = ["store_name"]

    # ── Filters ────────────────────────────────────────────────────
    list_filter = [
        "is_verified",
        "is_active",
        "is_featured",
        "country",
        OnboardingStatusFilter,
        HasPayoutProfileFilter,
        HasProductsFilter,
        ("created_at", admin.DateFieldListFilter),
    ]

    # ── Search ─────────────────────────────────────────────────────
    search_fields = [
        "user__email",
        "store_name",
        "store_slug",
        "city",
        "state",
    ]
    search_help_text = "Search by email, store name, slug, city or state."

    # ── Date drill-down ────────────────────────────────────────────
    date_hierarchy = "created_at"

    # ── Ordering ───────────────────────────────────────────────────
    ordering = ["-created_at"]

    # ── Read-only & editable fields ────────────────────────────────
    readonly_fields = [
        "store_slug",
        "created_at",
        "updated_at",
        "total_products",
        "total_sales",
        "total_revenue",
        "average_rating",
        "review_count",
        "wallet_balance",
        "user_email",
    ]

    # ── Fieldsets ──────────────────────────────────────────────────
    fieldsets = [
        (
            "🏪 Store Identity",
            {"fields": ["user", "store_name", "store_slug", "tagline", "description"]},
        ),
        (
            "🖼️ Media",
            {"fields": ["logo_url", "cover_url"], "classes": ["collapse"]},
        ),
        (
            "📍 Location & Hours",
            {
                "fields": [
                    "city", "state", "country",
                    "opening_time", "closing_time", "business_hours",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "🔗 Social Links",
            {
                "fields": [
                    "instagram_url", "tiktok_url", "twitter_url",
                    "website_url", "whatsapp",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "📊 Analytics (computed — do NOT edit)",
            {
                "fields": [
                    "total_products", "total_sales", "total_revenue",
                    "average_rating", "review_count", "wallet_balance",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "🔐 Status & Security",
            {"fields": ["is_verified", "is_active", "is_featured"]},
        ),
        (
            "📅 Timestamps",
            {"fields": ["created_at", "updated_at"], "classes": ["collapse"]},
        ),
    ]

    # ── Inlines ────────────────────────────────────────────────────
    inlines = [VendorSetupStateInline, VendorPayoutProfileInline]

    # ── Raw ID fields (for large FK targets) ──────────────────────
    raw_id_fields = ["user"]

    # ── List Select ────────────────────────────────────────────────
    def get_queryset(self, request):
        """
        Add select_related + prefetch_related to avoid N+1 on list_display.
        Annotate with computed order count for display if needed.
        """
        return (
            super().get_queryset(request)
            .select_related("user", "setup_state", "payout_profile")
            .prefetch_related("collections")
        )

    # ── Computed columns ───────────────────────────────────────────

    @admin.display(description="User Email")
    def user_email(self, obj: VendorProfile) -> str:
        return getattr(obj.user, "email", "—")

    @admin.display(description="Onboarding", boolean=False)
    def onboarding_status_badge(self, obj: VendorProfile) -> str:
        """
        Visual onboarding progress badge.
        Reads from the pre-fetched setup_state reverse OneToOne.
        """
        try:
            state = obj.setup_state
            pct   = state.completion_percentage
            if state.onboarding_done:
                return format_html('<span style="color:green;font-weight:bold">✅ Live ({}%)</span>', pct)
            return format_html('<span style="color:orange">⏳ Step {}/4 ({}%)</span>', state.current_step, pct)
        except VendorSetupState.DoesNotExist:
            return format_html('<span style="color:red">❌ Not Started</span>')
    onboarding_status_badge.allow_tags = True  # Django admin legacy support

    @admin.display(description="Revenue (₦)")
    def revenue_display(self, obj: VendorProfile) -> str:
        """Format total_revenue as Nigerian Naira."""
        return f"₦{obj.total_revenue:,.2f}"

    # ── Custom Admin Actions ───────────────────────────────────────

    @admin.action(description="✅ Mark selected vendors as VERIFIED")
    def verify_vendors(self, request, queryset: QuerySet) -> None:
        updated = queryset.update(is_verified=True)
        logger.info(
            "Admin action verify_vendors: %d vendors verified by %s",
            updated, request.user.email,
        )
        self.message_user(
            request,
            f"{updated} vendor(s) marked as verified.",
            messages.SUCCESS,
        )

    @admin.action(description="❌ Mark selected vendors as UNVERIFIED")
    def unverify_vendors(self, request, queryset: QuerySet) -> None:
        updated = queryset.update(is_verified=False)
        self.message_user(
            request,
            f"{updated} vendor(s) marked as unverified.",
            messages.WARNING,
        )

    @admin.action(description="🔴 SUSPEND selected vendors (deactivate)")
    def suspend_vendors(self, request, queryset: QuerySet) -> None:
        updated = queryset.update(is_active=False)
        logger.warning(
            "Admin action suspend_vendors: %d vendors suspended by %s",
            updated, request.user.email,
        )
        self.message_user(
            request,
            f"{updated} vendor(s) suspended.",
            messages.ERROR,
        )

    @admin.action(description="🟢 REACTIVATE selected vendors")
    def reactivate_vendors(self, request, queryset: QuerySet) -> None:
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f"{updated} vendor(s) reactivated.",
            messages.SUCCESS,
        )

    @admin.action(description="⭐ Mark selected vendors as FEATURED")
    def feature_vendors(self, request, queryset: QuerySet) -> None:
        updated = queryset.update(is_featured=True)
        self.message_user(
            request,
            f"{updated} vendor(s) marked as featured.",
            messages.SUCCESS,
        )

    @admin.action(description="☆ Remove FEATURED status from selected vendors")
    def unfeature_vendors(self, request, queryset: QuerySet) -> None:
        updated = queryset.update(is_featured=False)
        self.message_user(
            request,
            f"{updated} vendor(s) removed from featured.",
            messages.WARNING,
        )

    actions = [
        "verify_vendors",
        "unverify_vendors",
        "suspend_vendors",
        "reactivate_vendors",
        "feature_vendors",
        "unfeature_vendors",
    ]


# ══════════════════════════════════════════════════════════════════
#  VendorSetupState Admin (standalone view — rare use, inlined above)
# ══════════════════════════════════════════════════════════════════


@admin.register(VendorSetupState)
class VendorSetupStateAdmin(admin.ModelAdmin):
    """
    Standalone admin for VendorSetupState.
    Typically viewed inline on VendorProfile, but registered for direct access.
    """
    list_display  = [
        "vendor_store_name",
        "vendor_email",
        "current_step",
        "profile_complete",
        "bank_details",
        "first_product",
        "onboarding_done",
        "id_verified",      # informational — KYC future sprint
    ]
    list_filter   = [
        "onboarding_done",
        "profile_complete",
        "bank_details",
        "first_product",
        "id_verified",
    ]
    search_fields = ["vendor__user__email", "vendor__store_name"]
    ordering      = ["-updated_at"]
    readonly_fields = [
        "profile_complete",
        "bank_details",
        "first_product",
        "onboarding_done",
        "current_step",
        "created_at",
        "updated_at",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("vendor", "vendor__user")

    @admin.display(description="Store Name")
    def vendor_store_name(self, obj: VendorSetupState) -> str:
        return obj.vendor.store_name or f"Vendor #{obj.vendor.pk}"

    @admin.display(description="Email")
    def vendor_email(self, obj: VendorSetupState) -> str:
        return getattr(obj.vendor.user, "email", "—")


# ══════════════════════════════════════════════════════════════════
#  VendorPayoutProfile Admin
# ══════════════════════════════════════════════════════════════════


@admin.register(VendorPayoutProfile)
class VendorPayoutProfileAdmin(admin.ModelAdmin):
    """
    Admin for VendorPayoutProfile.
    Encrypted account number is NEVER displayed — only last 4 digits.
    Staff can verify bank accounts from this view.
    """
    list_display  = [
        "vendor_store_name",
        "vendor_email",
        "bank_name",
        "account_name",
        "account_last4_display",
        "paystack_recipient_code",
        "is_verified",
        "created_at",
    ]
    list_filter   = ["is_verified", "bank_name"]
    search_fields = [
        "vendor__user__email",
        "vendor__store_name",
        "account_name",
        "bank_name",
    ]
    ordering      = ["-created_at"]
    readonly_fields = [
        "account_number_enc",    # always read-only — encrypted blob
        "account_last4",
        "created_at",
        "updated_at",
    ]
    fieldsets = [
        (
            "🏦 Bank Details",
            {"fields": ["vendor", "bank_name", "bank_code", "account_name"]},
        ),
        (
            "🔐 Encrypted Account Number",
            {
                "fields": ["account_number_enc", "account_last4"],
                "description": (
                    "⚠️ The full account number is Fernet-encrypted. "
                    "Only the last 4 digits are shown here for verification."
                ),
            },
        ),
        (
            "💸 Paystack",
            {"fields": ["paystack_recipient_code"], "classes": ["collapse"]},
        ),
        (
            "✅ Verification",
            {"fields": ["is_verified"]},
        ),
        (
            "📅 Timestamps",
            {"fields": ["created_at", "updated_at"], "classes": ["collapse"]},
        ),
    ]

    # ── Custom bulk action ─────────────────────────────────────────

    @admin.action(description="✅ Mark selected payout profiles as VERIFIED")
    def verify_payout_profiles(self, request, queryset: QuerySet) -> None:
        updated = queryset.update(is_verified=True)
        logger.info(
            "Admin action verify_payout_profiles: %d profiles verified by %s",
            updated, request.user.email,
        )
        self.message_user(
            request,
            f"{updated} payout profile(s) verified.",
            messages.SUCCESS,
        )

    @admin.action(description="❌ Mark selected payout profiles as UNVERIFIED")
    def unverify_payout_profiles(self, request, queryset: QuerySet) -> None:
        updated = queryset.update(is_verified=False)
        self.message_user(
            request,
            f"{updated} payout profile(s) marked unverified.",
            messages.WARNING,
        )

    actions = ["verify_payout_profiles", "unverify_payout_profiles"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("vendor", "vendor__user")

    @admin.display(description="Store")
    def vendor_store_name(self, obj: VendorPayoutProfile) -> str:
        return obj.vendor.store_name or f"Vendor #{obj.vendor.pk}"

    @admin.display(description="Email")
    def vendor_email(self, obj: VendorPayoutProfile) -> str:
        return getattr(obj.vendor.user, "email", "—")

    @admin.display(description="Acct ****")
    def account_last4_display(self, obj: VendorPayoutProfile) -> str:
        last4 = obj.account_last4 or "????"
        return f"****{last4}"
