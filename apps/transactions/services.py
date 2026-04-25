from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.transactions.models import (
    CommissionRule,
    CompanyRevenueEntry,
    RevenueCategory,
    Transaction,
    TransactionDirection,
    TransactionDispute,
    TransactionLog,
    TransactionStatus,
    TransactionType,
)


class CommissionService:
    DEFAULT_RATE = Decimal("0.1000")
    MEASUREMENT_FEE_NGN = Decimal("1000.00")

    @classmethod
    def rate_for_vendor(cls, vendor_user) -> Decimal:
        rule = (
            CommissionRule.objects.filter(vendor_user=vendor_user, is_active=True)
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now()))
            .order_by("-starts_at")
            .first()
        )
        return rule.rate if rule else cls.DEFAULT_RATE

    @staticmethod
    def calculate(amount: Decimal, rate: Decimal) -> Decimal:
        return (amount * rate).quantize(Decimal("0.01"))


class TransactionLedgerService:
    @staticmethod
    def _log(txn: Transaction, new_status: str, previous_status: str = "", reason: str = "") -> None:
        TransactionLog.objects.create(
            transaction=txn,
            previous_status=previous_status,
            new_status=new_status,
            reason=reason,
        )

    @classmethod
    def create_entry(cls, **kwargs) -> Transaction:
        txn = Transaction.objects.create(**kwargs)
        cls._log(txn, txn.status, reason="Transaction created")
        return txn

    @classmethod
    def complete(cls, txn: Transaction, reason: str = "Transaction completed") -> Transaction:
        previous = txn.status
        txn.complete()
        txn.save(update_fields=["status", "processed_at", "completed_at", "updated_at"])
        cls._log(txn, txn.status, previous_status=previous, reason=reason)
        return txn

    @classmethod
    def record_escrow_hold(cls, *, user, wallet, amount: Decimal, reference: str, order_id: str = "", provider_reference: str = "", idempotency_key: str = "") -> Transaction:
        txn = cls.create_entry(
            transaction_type=TransactionType.ESCROW_HOLD,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.OUTBOUND,
            amount=amount,
            net_amount=amount,
            from_user=user,
            from_wallet=wallet,
            reference=f"{reference}:hold",
            provider_reference=provider_reference,
            idempotency_key=idempotency_key,
            order_id=order_id,
            description="Client order payment held in Fashionistar escrow.",
            completed_at=timezone.now(),
        )
        return txn

    @classmethod
    def record_escrow_release(cls, *, hold, vendor_user, vendor_wallet, company_wallet, gross_amount: Decimal, vendor_amount: Decimal, commission_amount: Decimal, idempotency_key: str = "") -> None:
        cls.create_entry(
            transaction_type=TransactionType.ESCROW_RELEASE,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.INBOUND,
            amount=vendor_amount,
            net_amount=vendor_amount,
            to_user=vendor_user,
            to_wallet=vendor_wallet,
            reference=f"{hold.reference}:vendor-release",
            idempotency_key=idempotency_key,
            order_id=hold.order_id,
            description="Escrow released to vendor after client confirmation.",
            completed_at=timezone.now(),
        )
        commission_txn = cls.create_entry(
            transaction_type=TransactionType.COMMISSION,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.INBOUND,
            amount=commission_amount,
            net_amount=commission_amount,
            to_wallet=company_wallet,
            reference=f"{hold.reference}:company-commission",
            idempotency_key=idempotency_key,
            order_id=hold.order_id,
            description="Fashionistar commission credited to company wallet.",
            completed_at=timezone.now(),
            metadata={"gross_amount": str(gross_amount)},
        )
        CompanyRevenueEntry.objects.create(
            transaction=commission_txn,
            category=RevenueCategory.ORDER_COMMISSION,
            amount=commission_amount,
            currency=company_wallet.currency,
            source_reference=hold.reference,
            metadata={"order_id": hold.order_id, "gross_amount": str(gross_amount)},
        )

    @classmethod
    def record_refund(cls, *, wallet, amount: Decimal, reference: str, order_id: str = "", idempotency_key: str = "") -> Transaction:
        return cls.create_entry(
            transaction_type=TransactionType.REFUND,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.INBOUND,
            amount=amount,
            net_amount=amount,
            to_user=wallet.user,
            to_wallet=wallet,
            reference=f"{reference}:refund",
            idempotency_key=idempotency_key,
            order_id=order_id,
            description="Escrow refund returned to client wallet.",
            completed_at=timezone.now(),
        )

    @classmethod
    @db_transaction.atomic
    def record_measurement_fee(cls, *, user, wallet, company_wallet, reference: str, amount: Decimal | None = None, measurement_request_id: str = "", idempotency_key: str = "") -> Transaction:
        amount = amount or CommissionService.MEASUREMENT_FEE_NGN
        if wallet.available_balance < amount:
            raise ValidationError("Insufficient balance for measurement fee.")
        wallet.available_balance -= amount
        wallet.balance -= amount
        company_wallet.available_balance += amount
        company_wallet.balance += amount
        wallet.save(update_fields=["available_balance", "balance", "updated_at"])
        company_wallet.save(update_fields=["available_balance", "balance", "updated_at"])
        txn = cls.create_entry(
            transaction_type=TransactionType.MEASUREMENT_FEE,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.INBOUND,
            amount=amount,
            net_amount=amount,
            from_user=user,
            from_wallet=wallet,
            to_wallet=company_wallet,
            reference=reference,
            idempotency_key=idempotency_key,
            measurement_request_id=measurement_request_id,
            description="Digital precision measurement processing fee.",
            completed_at=timezone.now(),
        )
        CompanyRevenueEntry.objects.create(
            transaction=txn,
            category=RevenueCategory.MEASUREMENT_SERVICE,
            amount=amount,
            currency=company_wallet.currency,
            source_reference=reference,
            metadata={"measurement_request_id": measurement_request_id},
        )
        return txn


class TransactionQueryService:
    @staticmethod
    def for_user(user):
        return (
            Transaction.objects.filter(Q(from_user=user) | Q(to_user=user) | Q(from_wallet__user=user) | Q(to_wallet__user=user))
            .select_related("from_user", "to_user", "from_wallet", "to_wallet", "from_wallet__currency", "to_wallet__currency")
            .order_by("-created_at")
        )

    @classmethod
    def summary_for_user(cls, user) -> dict:
        qs = cls.for_user(user)
        return {
            "total_transactions": qs.count(),
            "completed": qs.filter(status=TransactionStatus.COMPLETED).count(),
            "pending": qs.filter(status__in=[TransactionStatus.PENDING, TransactionStatus.PROCESSING]).count(),
            "total_sent": qs.filter(Q(from_user=user) | Q(from_wallet__user=user)).aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
            "total_received": qs.filter(Q(to_user=user) | Q(to_wallet__user=user)).aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
        }


class DisputeService:
    @staticmethod
    def create_dispute(*, user, transaction_id, reason: str, amount: Decimal) -> TransactionDispute:
        txn = TransactionQueryService.for_user(user).get(pk=transaction_id)
        dispute = TransactionDispute.objects.create(
            transaction=txn,
            initiated_by=user,
            reason=reason,
            disputed_amount=amount,
        )
        previous = txn.status
        txn.status = TransactionStatus.DISPUTED
        txn.save(update_fields=["status", "updated_at"])
        TransactionLog.objects.create(transaction=txn, previous_status=previous, new_status=txn.status, changed_by=user, reason="Dispute opened")
        return dispute
