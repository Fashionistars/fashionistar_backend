from django.contrib import admin

from apps.wallet.models import Currency, Wallet, WalletHold


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol", "is_active", "exchange_rate_usd")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "owner_type", "currency", "balance", "available_balance", "pending_balance", "escrow_balance", "status")
    list_filter = ("owner_type", "currency", "status", "is_default")
    search_fields = ("name", "user__email", "user__phone", "account_number")
    readonly_fields = ("pin_hash", "pin_set_at", "last_transaction_at", "created_at", "updated_at")


@admin.register(WalletHold)
class WalletHoldAdmin(admin.ModelAdmin):
    list_display = ("reference", "order_id", "wallet", "amount", "released_amount", "refunded_amount", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("reference", "order_id", "wallet__user__email")
