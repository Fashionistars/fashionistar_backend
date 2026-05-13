# apps/wallet/admin.py
"""
Django admin configuration for the Wallet domain.

Includes:
  - CurrencyAdmin          : Manage platform currencies.
  - WalletAdmin            : Monitor user and company wallets.
  - WalletHoldAdmin        : Inspect escrow holds.
  - PayoutWithdrawalAdmin  : Admin approval/rejection panel for
                             PROCESSING PAYOUT withdrawal requests.

Admin Payout Flow (P1 Sprint):
  1. Admin opens "Pending Payouts" changelist (filtered to PROCESSING PAYOUT).
  2. Selects one or more rows and uses bulk actions:
       - "Confirm payouts" → marks COMPLETED, zeroes pending_balance.
       - "Reject payouts"  → marks FAILED, restores to available_balance.
  3. Each action fires a user notification and a compliance audit trail.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.contrib import admin, messages
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.wallet.models import Currency, Wallet, WalletHold

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CURRENCY
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol", "is_active", "exchange_rate_usd")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


# ─────────────────────────────────────────────────────────────────────────────
# WALLET
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = (
        "name", "user", "owner_type", "currency",
        "balance", "available_balance", "pending_balance",
        "escrow_balance", "status",
    )
    list_filter = ("owner_type", "currency", "status", "is_default")
    search_fields = ("name", "user__email", "user__phone", "account_number")
    readonly_fields = (
        "pin_hash", "pin_set_at", "last_transaction_at", "created_at", "updated_at",
    )


# ─────────────────────────────────────────────────────────────────────────────
# WALLET HOLD
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(WalletHold)
class WalletHoldAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "order_id", "wallet", "amount",
        "released_amount", "refunded_amount", "status", "created_at",
    )
    list_filter = ("status",)
    search_fields = ("reference", "order_id", "wallet__user__email")


# ─────────────────────────────────────────────────────────────────────────────
# PAYOUT WITHDRAWAL APPROVAL (Proxy Model + ModelAdmin)
# ─────────────────────────────────────────────────────────────────────────────

class PendingPayoutTransaction(admin.ModelAdmin):
    """
    Admin panel for PAYOUT withdrawal request approval/rejection.

    Registered against apps.transactions.Transaction (PAYOUT type)
    via a proxy queryset — no separate model needed.

    Bulk actions:
      confirm_payouts — Mark selected PROCESSING payouts as COMPLETED,
                        zero their pending_balance on the linked wallet.
      reject_payouts  — Mark selected PROCESSING payouts as FAILED,
                        restore funds to available_balance.
    """
    list_display = (
        "reference", "from_user_email", "amount", "status",
        "bank_code", "account_number_last4", "created_at",
    )
    list_filter = ("status",)
    search_fields = (
        "reference", "from_user__email", "from_user__phone",
    )
    readonly_fields = (
        "reference", "transaction_type", "status", "amount", "net_amount",
        "from_user", "from_wallet", "metadata",
        "initiated_at", "processed_at", "completed_at", "failed_at",
        "created_at", "updated_at",
    )
    actions = ["confirm_payouts", "reject_payouts"]

    def get_queryset(self, request):
        from apps.transactions.models import Transaction, TransactionType
        return (
            Transaction.objects.filter(transaction_type=TransactionType.PAYOUT)
            .select_related("from_user", "from_wallet")
            .order_by("-created_at")
        )

    def from_user_email(self, obj) -> str:
        return getattr(obj.from_user, "email", "—")
    from_user_email.short_description = "User Email"

    def bank_code(self, obj) -> str:
        return (obj.metadata or {}).get("bank_code", "—")
    bank_code.short_description = "Bank Code"

    def account_number_last4(self, obj) -> str:
        return (obj.metadata or {}).get("account_number_last4", "—")
    account_number_last4.short_description = "Account (last 4)"

    # ── Bulk Actions ──────────────────────────────────────────────────────────

    @admin.action(description="✅ Confirm selected payouts (mark COMPLETED)")
    def confirm_payouts(self, request, queryset):
        from apps.transactions.models import TransactionStatus

        processing = queryset.filter(status=TransactionStatus.PROCESSING)
        confirmed = 0
        for txn in processing.select_related("from_wallet", "from_user"):
            try:
                self._confirm_one(txn, request.user)
                confirmed += 1
            except Exception as exc:
                self.message_user(
                    request,
                    f"Failed to confirm txn {txn.reference}: {exc}",
                    messages.ERROR,
                )

        if confirmed:
            self.message_user(
                request,
                f"✅ Confirmed {confirmed} payout(s).",
                messages.SUCCESS,
            )

    @admin.action(description="❌ Reject selected payouts (mark FAILED, restore funds)")
    def reject_payouts(self, request, queryset):
        from apps.transactions.models import TransactionStatus

        processing = queryset.filter(status=TransactionStatus.PROCESSING)
        rejected = 0
        for txn in processing.select_related("from_wallet", "from_user"):
            try:
                self._reject_one(txn, request.user)
                rejected += 1
            except Exception as exc:
                self.message_user(
                    request,
                    f"Failed to reject txn {txn.reference}: {exc}",
                    messages.ERROR,
                )

        if rejected:
            self.message_user(
                request,
                f"❌ Rejected {rejected} payout(s). Funds restored to user wallets.",
                messages.WARNING,
            )

    # ── Internal helpers ──────────────────────────────────────────────────────

    @db_transaction.atomic
    def _confirm_one(self, txn, admin_user) -> None:
        from apps.transactions.models import TransactionStatus

        wallet = txn.from_wallet
        if wallet:
            locked = wallet.__class__.objects.select_for_update().get(pk=wallet.pk)
            amount = txn.amount or Decimal("0.00")
            locked.pending_balance = max(locked.pending_balance - amount, Decimal("0.00"))
            locked.last_transaction_at = timezone.now()
            locked.save(update_fields=["pending_balance", "last_transaction_at", "updated_at"])

        txn.status = TransactionStatus.COMPLETED
        txn.completed_at = timezone.now()
        txn.metadata = {**(txn.metadata or {}), "payout_state": "admin_confirmed", "confirmed_by": str(admin_user.pk)}
        txn.save(update_fields=["status", "completed_at", "metadata"])

        _notify_payout_user(txn, success=True)
        _audit_admin_payout(txn, admin_user, success=True)

    @db_transaction.atomic
    def _reject_one(self, txn, admin_user) -> None:
        from apps.transactions.models import TransactionStatus

        wallet = txn.from_wallet
        if wallet:
            locked = wallet.__class__.objects.select_for_update().get(pk=wallet.pk)
            amount = txn.amount or Decimal("0.00")
            locked.pending_balance = max(locked.pending_balance - amount, Decimal("0.00"))
            locked.available_balance += amount
            locked.last_transaction_at = timezone.now()
            locked.save(update_fields=["pending_balance", "available_balance", "last_transaction_at", "updated_at"])

        txn.status = TransactionStatus.FAILED
        txn.failed_at = timezone.now()
        txn.metadata = {**(txn.metadata or {}), "payout_state": "admin_rejected", "rejected_by": str(admin_user.pk)}
        txn.save(update_fields=["status", "failed_at", "metadata"])

        _notify_payout_user(txn, success=False)
        _audit_admin_payout(txn, admin_user, success=False)


# ─────────────────────────────────────────────────────────────────────────────
# Notification + Audit helpers (fail-safe, called from admin actions)
# ─────────────────────────────────────────────────────────────────────────────

def _notify_payout_user(txn, *, success: bool) -> None:
    try:
        from apps.notification.models import NotificationChannel, NotificationType
        from apps.notification.services import create_notification

        if txn.from_user is None:
            return
        amount_str = f"₦{txn.amount:,.2f}" if txn.amount else "Your funds"

        if success:
            create_notification(
                recipient=txn.from_user,
                notification_type=NotificationType.PAYOUT_COMPLETED,
                title="Withdrawal Successful 🎉",
                body=(
                    f"{amount_str} has been sent to your bank account. "
                    "It may take 1–3 business days to reflect."
                ),
                channel=NotificationChannel.IN_APP,
                metadata={"transaction_id": str(txn.pk), "amount": str(txn.amount)},
            )
        else:
            create_notification(
                recipient=txn.from_user,
                notification_type=NotificationType.PAYOUT_COMPLETED,
                title="Withdrawal Rejected",
                body=(
                    f"Your withdrawal of {amount_str} was not approved. "
                    "The funds have been returned to your available wallet balance. "
                    "Contact support for assistance."
                ),
                channel=NotificationChannel.IN_APP,
                metadata={"transaction_id": str(txn.pk), "amount": str(txn.amount)},
            )
    except Exception as exc:
        logger.warning("_notify_payout_user failed: %s", exc)


def _audit_admin_payout(txn, admin_user, *, success: bool) -> None:
    try:
        from apps.audit_logs.services.wallet import wallet_audit
        if success:
            wallet_audit.log_payout_confirmed(
                actor=admin_user,
                wallet_id=str(getattr(txn.from_wallet, "pk", "")),
                transaction_id=str(txn.pk),
                amount=str(txn.amount),
            )
        else:
            wallet_audit.log_payout_failed(
                actor=admin_user,
                wallet_id=str(getattr(txn.from_wallet, "pk", "")),
                transaction_id=str(txn.pk),
                amount=str(txn.amount),
            )
    except Exception as exc:
        logger.warning("_audit_admin_payout failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Register the payout approval panel against Transaction model
# ─────────────────────────────────────────────────────────────────────────────

def _register_payout_admin():
    """Late-register the payout admin against Transaction without circular imports."""
    try:
        from apps.transactions.models import Transaction

        # Only register if not already registered by transactions/admin.py
        if not admin.site.is_registered(Transaction):
            admin.site.register(Transaction, PendingPayoutTransaction)
        else:
            # Already registered — inject our actions into the existing admin
            existing_admin = admin.site._registry.get(Transaction)
            if existing_admin and not hasattr(existing_admin, "_wallet_payout_actions_injected"):
                existing_admin.actions = list(getattr(existing_admin, "actions", []) or []) + [
                    PendingPayoutTransaction.confirm_payouts,
                    PendingPayoutTransaction.reject_payouts,
                ]
                existing_admin._wallet_payout_actions_injected = True
    except Exception as exc:
        logger.debug("_register_payout_admin: %s (non-critical)", exc)


# Run at Django startup (admin autodiscover calls this module)
_register_payout_admin()
