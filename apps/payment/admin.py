# apps/payment/admin.py
"""
Django Admin for the Payment domain.

Models registered:
  - PaymentIntent              : Payment initiation ledger (READ-ONLY)
  - PaymentWebhookEvent        : Incoming webhook audit log (READ-ONLY)
  - PaymentProvider            : Gateway configuration
  - PaymentProviderLog         : Provider API call log (READ-ONLY)
  - PaystackTransferRecipient  : Payout bank recipient records

Production rules:
  - PaymentIntent: all financial/gateway fields are read-only
  - PaymentWebhookEvent: immutable audit log (no add/change/delete)
  - PaymentProviderLog: immutable API call audit (no add/change/delete)
  - PaymentProvider: editable gateway config (staff only)
  - PaystackTransferRecipient: bank_code/account_number are readonly

2026 features:
  - Status badge with colour coding
  - Provider badge (paystack/stripe/flutterwave)
  - Processed/failed badge for webhook events
  - list_per_page = 25, show_full_result_count = False
  - date_hierarchy on all time-series models
"""
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.payment.models import (
    PaymentIntent,
    PaymentProvider,
    PaymentProviderLog,
    PaymentWebhookEvent,
    PaystackTransferRecipient,
)

logger = logging.getLogger(__name__)

# ── Provider badge colours ────────────────────────────────────────────────────
_PROVIDER_COLOURS = {
    "paystack":    ("#0ea5e9", "#fff"),
    "flutterwave": ("#f97316", "#fff"),
    "stripe":      ("#6366f1", "#fff"),
    "wallet":      ("#10b981", "#fff"),
}

_STATUS_COLOURS = {
    "pending":    "#f59e0b",
    "initiated":  "#3b82f6",
    "processing": "#8b5cf6",
    "completed":  "#10b981",
    "failed":     "#ef4444",
    "cancelled":  "#6b7280",
    "reversed":   "#dc2626",
    "expired":    "#94a3b8",
}


# ── Payment Intent Admin ──────────────────────────────────────────────────────

@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    """
    Primary payment initiation ledger — ALL financial fields are read-only.
    Fields verified against apps/payment/models.py.
    """

    list_display = [
        "reference", "user", "purpose", "provider_badge",
        "amount_display", "currency", "status_badge",
        "created_at",
    ]
    list_filter = ["provider", "purpose", "status", "currency"]
    search_fields = [
        "reference", "provider_reference",
        "user__email", "order_id",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["user"]
    raw_id_fields = ["user"]
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        "id", "reference", "user", "purpose", "provider",
        "amount", "currency", "status",
        "provider_reference", "order_id",
        "authorization_url", "access_code",
        "measurement_request_id", "idempotency_key",
        "provider_response", "metadata",
        "created_at", "updated_at",
    ]

    fieldsets = (
        (_("Identity"), {
            "fields": ("id", "reference", "user"),
        }),
        (_("Payment Details"), {
            "fields": (
                "purpose", "provider", "amount", "currency", "status",
            ),
        }),
        (_("Gateway"), {
            "fields": (
                "provider_reference", "order_id",
                "authorization_url", "access_code",
                "measurement_request_id", "idempotency_key",
                "provider_response",
            ),
        }),
        (_("Metadata"), {
            "fields": ("metadata",),
            "classes": ("collapse",),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Status")
    def status_badge(self, obj):
        bg = _STATUS_COLOURS.get(obj.status, "#6b7280")
        label = obj.get_status_display() if hasattr(obj, "get_status_display") else obj.status
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, label,
        )

    @admin.display(description="Provider")
    def provider_badge(self, obj):
        bg, fg = _PROVIDER_COLOURS.get(obj.provider, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.provider.upper(),
        )

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return format_html(
            '<strong style="color:#1e293b">₦{:,.2f}</strong>',
            obj.amount,
        )


# ── Payment Webhook Event Admin ───────────────────────────────────────────────

@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    """
    Immutable audit log of all incoming payment gateway webhooks.
    """

    list_display = [
        "provider_badge", "event_display", "reference",
        "processed_badge", "created_at",
    ]
    list_filter = ["provider", "event", "processed"]
    search_fields = ["reference", "event_id", "payload_hash"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        f.name for f in PaymentWebhookEvent._meta.get_fields()
        if hasattr(f, "name")
    ]

    fieldsets = (
        (_("Event"), {
            "fields": ("provider", "event", "event_id", "reference", "processed"),
        }),
        (_("Processing"), {
            "fields": ("processing_error", "payload_hash"),
        }),
        (_("Payload"), {
            "fields": ("payload",),
            "classes": ("collapse",),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Provider")
    def provider_badge(self, obj):
        bg, fg = _PROVIDER_COLOURS.get(obj.provider, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.provider.upper(),
        )

    @admin.display(description="Event")
    def event_display(self, obj):
        return format_html(
            '<code style="font-size:11px;color:#4b5563">{}</code>',
            obj.event,
        )

    @admin.display(description="Processed", boolean=True)
    def processed_badge(self, obj):
        return obj.processed


# ── Payment Provider Admin ────────────────────────────────────────────────────

@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    """
    Gateway configuration — editable by staff. Only exposes actual fields.
    Verified against model: code, name, is_active, metadata.
    """

    list_display = [
        "code", "name", "is_active", "created_at",
    ]
    list_filter = ["is_active"]
    search_fields = ["name", "code"]
    ordering = ["-is_active", "name"]
    list_per_page = 25
    empty_value_display = "-N/A-"

    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (_("Identity"), {
            "fields": ("code", "name"),
        }),
        (_("Status"), {
            "fields": ("is_active",),
        }),
        (_("Configuration"), {
            "fields": ("metadata",),
            "classes": ("collapse",),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


# ── Payment Provider Log Admin ────────────────────────────────────────────────

@admin.register(PaymentProviderLog)
class PaymentProviderLogAdmin(admin.ModelAdmin):
    """
    Immutable API call log for each interaction with a payment gateway.
    Fields: provider, action, reference, success, request_payload,
            response_payload, error_message, created_at, updated_at.
    """

    list_display = [
        "provider", "action", "reference",
        "success", "created_at",
    ]
    list_filter = ["provider", "success"]
    search_fields = ["action", "reference", "error_message"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        f.name for f in PaymentProviderLog._meta.get_fields()
        if hasattr(f, "name")
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ── Paystack Transfer Recipient Admin ─────────────────────────────────────────

@admin.register(PaystackTransferRecipient)
class PaystackTransferRecipientAdmin(admin.ModelAdmin):
    """
    Bank recipient records for Paystack payouts.
    Fields: user, recipient_code, account_number, account_name,
            bank_name, bank_code, provider_response, is_active.
    """

    list_display = [
        "user", "account_name", "bank_name",
        "account_number_masked", "is_active", "created_at",
    ]
    list_filter = ["bank_name", "is_active"]
    search_fields = [
        "user__email", "account_name",
        "recipient_code", "bank_name",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["user"]
    raw_id_fields = ["user"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        "user", "recipient_code",
        "bank_code", "account_number",
        "provider_response",
        "created_at", "updated_at",
    ]

    fieldsets = (
        (_("Account"), {
            "fields": (
                "user", "account_name", "bank_name",
                "bank_code", "account_number",
            ),
        }),
        (_("Paystack"), {
            "fields": ("recipient_code",),
        }),
        (_("Status"), {
            "fields": ("is_active",),
        }),
        (_("Provider Response"), {
            "fields": ("provider_response",),
            "classes": ("collapse",),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Account No.")
    def account_number_masked(self, obj):
        acct = obj.account_number or ""
        if len(acct) > 4:
            return f"{'*' * (len(acct) - 4)}{acct[-4:]}"
        return acct
