from django.contrib import admin

from apps.transactions.models import (
    CommissionRule,
    CompanyRevenueEntry,
    Transaction,
    TransactionDispute,
    TransactionFee,
    TransactionIdempotencyKey,
    TransactionLog,
)


class TransactionFeeInline(admin.TabularInline):
    model = TransactionFee
    extra = 0


class TransactionLogInline(admin.TabularInline):
    model = TransactionLog
    extra = 0
    readonly_fields = ("previous_status", "new_status", "changed_by", "reason", "metadata", "created_at")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("reference", "transaction_type", "status", "amount", "fee_amount", "order_id", "created_at")
    list_filter = ("transaction_type", "status", "direction")
    search_fields = ("reference", "external_reference", "provider_reference", "order_id", "from_user__email", "to_user__email")
    readonly_fields = ("created_at", "updated_at", "initiated_at", "processed_at", "completed_at", "failed_at")
    inlines = [TransactionFeeInline, TransactionLogInline]


@admin.register(TransactionDispute)
class TransactionDisputeAdmin(admin.ModelAdmin):
    list_display = ("transaction", "initiated_by", "status", "disputed_amount", "created_at")
    list_filter = ("status",)
    search_fields = ("transaction__reference", "initiated_by__email")


admin.site.register(TransactionIdempotencyKey)
admin.site.register(CommissionRule)
admin.site.register(CompanyRevenueEntry)
