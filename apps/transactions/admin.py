# apps/transactions/admin.py
"""
Django Admin for the Transactions financial domain.

Models registered:
  - Transaction              : Main financial ledger entry (READ-ONLY)
  - TransactionDispute       : Dispute management with resolution actions
  - TransactionIdempotencyKey: Idempotency tracking (READ-ONLY)
  - TransactionFee           : Fee breakdown (READ-ONLY inline + standalone)
  - TransactionLog           : Status transition log (immutable)
  - CommissionRule           : Platform commission rate configuration
  - CompanyRevenueEntry      : Revenue accounting (READ-ONLY)

Production rules:
  - ALL financial fields are readonly — no manual edits to transaction ledger
  - Status badges with colour coding
  - Transaction type badges
  - Admin disputes can be escalated or resolved via bulk actions
  - CSV export action available on Transaction list

2026 features:
  - NGN amount formatting helper
  - Dispute resolution action (superuser only)
  - list_select_related to prevent N+1 on user FKs
"""
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.http import StreamingHttpResponse
import csv

from apps.transactions.models import (
    CommissionRule,
    CompanyRevenueEntry,
    Transaction,
    TransactionDispute,
    TransactionFee,
    TransactionIdempotencyKey,
    TransactionLog,
)

logger = logging.getLogger(__name__)

# ── Status colours ────────────────────────────────────────────────────────────
_STATUS_COLOURS = {
    "pending":    ("#f59e0b", "#fff"),
    "processing": ("#3b82f6", "#fff"),
    "completed":  ("#10b981", "#fff"),
    "failed":     ("#ef4444", "#fff"),
    "cancelled":  ("#6b7280", "#fff"),
    "reversed":   ("#8b5cf6", "#fff"),
    "disputed":   ("#dc2626", "#fff"),
}

_TYPE_COLOURS = {
    "payment":          ("#6366f1", "#fff"),
    "payout":           ("#10b981", "#fff"),
    "refund":           ("#f59e0b", "#fff"),
    "commission":       ("#8b5cf6", "#fff"),
    "wallet_credit":    ("#06b6d4", "#fff"),
    "wallet_debit":     ("#ef4444", "#fff"),
    "escrow_hold":      ("#0ea5e9", "#fff"),
    "escrow_release":   ("#22c55e", "#fff"),
    "milestone_payment":("#7c3aed", "#fff"),
}


# ── Inlines ───────────────────────────────────────────────────────────────────

class TransactionFeeInline(admin.TabularInline):
    model = TransactionFee
    extra = 0
    readonly_fields = [
        f.name for f in TransactionFee._meta.get_fields()
        if hasattr(f, "name")
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class TransactionLogInline(admin.TabularInline):
    model = TransactionLog
    extra = 0
    readonly_fields = [
        "previous_status", "new_status", "changed_by",
        "reason", "metadata", "created_at",
    ]
    can_delete = False
    ordering = ["created_at"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ── Transaction Admin ─────────────────────────────────────────────────────────

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """
    Primary financial ledger admin — ALL fields are read-only.
    No manual modification of transaction records is permitted.
    """

    list_display = [
        "reference", "type_badge", "status_badge",
        "formatted_amount", "currency", "direction",
        "from_user", "to_user", "order_id",
        "initiated_at", "completed_at",
    ]
    list_filter = [
        "transaction_type", "status", "direction", "currency",
    ]
    search_fields = [
        "reference", "external_reference", "provider_reference",
        "order_id", "from_user__email", "to_user__email",
    ]
    ordering = ["-initiated_at"]
    date_hierarchy = "initiated_at"
    list_select_related = ["from_user", "to_user"]
    raw_id_fields = ["from_user", "to_user"]
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"

    # ALL financial fields must be read-only — no exceptions
    readonly_fields = [
        f.name for f in Transaction._meta.get_fields()
        if hasattr(f, "name")
    ]

    fieldsets = (
        (_("Identity"), {
            "fields": (
                "id", "reference", "external_reference",
                "provider_reference", "idempotency_key",
            ),
        }),
        (_("Parties"), {
            "fields": ("from_user", "to_user"),
        }),
        (_("Type & Status"), {
            "fields": (
                "transaction_type", "direction", "status",
            ),
        }),
        (_("Financials"), {
            "fields": (
                "amount", "fee_amount", "net_amount", "currency",
                "exchange_rate", "original_amount", "original_currency",
            ),
        }),
        (_("Context"), {
            "fields": (
                "order_id", "custom_order_id", "wallet_id",
                "provider", "gateway_response",
            ),
        }),
        (_("Timeline"), {
            "fields": (
                "initiated_at", "processed_at",
                "completed_at", "failed_at",
                "created_at", "updated_at",
            ),
            "classes": ("collapse",),
        }),
        (_("Metadata"), {
            "fields": ("metadata", "description", "failure_reason"),
            "classes": ("collapse",),
        }),
    )

    inlines = [TransactionFeeInline, TransactionLogInline]
    actions = ["export_csv"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # ── List display helpers ─────────────────────────────────────────────────

    @admin.display(description="Status")
    def status_badge(self, obj):
        bg, fg = _STATUS_COLOURS.get(obj.status, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.get_status_display() if hasattr(obj, "get_status_display") else obj.status,
        )

    @admin.display(description="Type")
    def type_badge(self, obj):
        bg, fg = _TYPE_COLOURS.get(obj.transaction_type, ("#6366f1", "#fff"))
        label = (
            obj.get_transaction_type_display()
            if hasattr(obj, "get_transaction_type_display")
            else obj.transaction_type
        )
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, label,
        )

    @admin.display(description="Amount (NGN)")
    def formatted_amount(self, obj):
        return format_html(
            '<strong style="color:#1e293b">₦{:,.2f}</strong>',
            obj.amount,
        )

    # ── CSV Export (streaming) ───────────────────────────────────────────────

    @admin.action(description="📥 Export selected transactions to CSV")
    def export_csv(self, request, queryset):
        fields = [
            "reference", "transaction_type", "status", "direction",
            "amount", "fee_amount", "currency",
            "from_user__email", "to_user__email",
            "order_id", "initiated_at", "completed_at",
        ]

        def rows():
            yield fields
            for row in queryset.values(*fields).iterator():
                yield [str(row.get(f, "") or "") for f in fields]

        def stream():
            import io
            for row in rows():
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(row)
                yield buf.getvalue()

        response = StreamingHttpResponse(stream(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="transactions.csv"'
        return response


# ── Transaction Dispute Admin ─────────────────────────────────────────────────

@admin.register(TransactionDispute)
class TransactionDisputeAdmin(admin.ModelAdmin):
    list_display = [
        "transaction", "initiated_by", "status_badge",
        "disputed_amount", "currency", "created_at",
    ]
    list_filter = ["status", "currency"]
    search_fields = ["transaction__reference", "initiated_by__email", "reason"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["transaction", "initiated_by"]
    raw_id_fields = ["transaction", "initiated_by"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        "transaction", "initiated_by", "disputed_amount", "currency",
        "created_at", "updated_at",
    ]

    fieldsets = (
        (_("Dispute"), {
            "fields": (
                "transaction", "initiated_by",
                "disputed_amount", "currency", "status",
            ),
        }),
        (_("Details"), {
            "fields": ("reason", "evidence_urls", "resolution_notes"),
        }),
        (_("Timeline"), {
            "fields": ("resolved_at", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["action_resolve_disputes"]

    @admin.display(description="Status")
    def status_badge(self, obj):
        colours = {
            "open":     ("#f59e0b", "#fff"),
            "resolved": ("#10b981", "#fff"),
            "escalated":("#dc2626", "#fff"),
            "closed":   ("#6b7280", "#fff"),
        }
        bg, fg = colours.get(obj.status, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.get_status_display() if hasattr(obj, "get_status_display") else obj.status,
        )

    @admin.action(description="✅ Mark selected disputes as Resolved (superuser only)")
    def action_resolve_disputes(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Superuser only.", level=messages.ERROR)
            return
        updated = queryset.exclude(status="resolved").update(status="resolved")
        self.message_user(
            request,
            f"✅ {updated} dispute(s) marked resolved.",
            level=messages.SUCCESS,
        )


# ── Transaction Fee Admin ─────────────────────────────────────────────────────

@admin.register(TransactionFee)
class TransactionFeeAdmin(admin.ModelAdmin):
    list_display = ["transaction", "fee_type", "amount", "currency", "created_at"]
    list_filter = ["fee_type", "currency"]
    search_fields = ["transaction__reference"]
    ordering = ["-created_at"]
    list_select_related = ["transaction"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        f.name for f in TransactionFee._meta.get_fields()
        if hasattr(f, "name")
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ── Transaction Log Admin (append-only) ───────────────────────────────────────

@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = [
        "transaction", "previous_status", "new_status",
        "changed_by", "created_at",
    ]
    list_filter = ["new_status", "previous_status"]
    search_fields = ["transaction__reference", "changed_by__email", "reason"]
    ordering = ["-created_at"]
    list_select_related = ["transaction", "changed_by"]
    date_hierarchy = "created_at"
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        f.name for f in TransactionLog._meta.get_fields()
        if hasattr(f, "name")
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ── Transaction Idempotency Key (read-only) ────────────────────────────────────

@admin.register(TransactionIdempotencyKey)
class TransactionIdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ["key", "transaction", "created_at"]
    search_fields = ["key", "transaction__reference"]
    ordering = ["-created_at"]
    list_select_related = ["transaction"]
    date_hierarchy = "created_at"
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        f.name for f in TransactionIdempotencyKey._meta.get_fields()
        if hasattr(f, "name")
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ── Commission Rule Admin ─────────────────────────────────────────────────────

@admin.register(CommissionRule)
class CommissionRuleAdmin(admin.ModelAdmin):
    list_display = [
        "name", "rate_pct", "applies_to", "is_active",
        "created_at", "updated_at",
    ]
    list_filter = ["is_active", "applies_to"]
    search_fields = ["name", "description"]
    ordering = ["-is_active", "rate_pct"]
    list_per_page = 25
    empty_value_display = "-N/A-"

    fieldsets = (
        (_("Rule"), {
            "fields": ("name", "applies_to", "rate_pct", "is_active"),
        }),
        (_("Details"), {
            "fields": ("description", "min_amount", "max_amount"),
            "classes": ("collapse",),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    readonly_fields = ["created_at", "updated_at"]


# ── Company Revenue Entry (read-only) ─────────────────────────────────────────

@admin.register(CompanyRevenueEntry)
class CompanyRevenueEntryAdmin(admin.ModelAdmin):
    list_display = [
        "transaction", "amount", "currency", "revenue_type",
        "created_at",
    ]
    list_filter = ["revenue_type", "currency"]
    search_fields = ["transaction__reference"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["transaction"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        f.name for f in CompanyRevenueEntry._meta.get_fields()
        if hasattr(f, "name")
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
