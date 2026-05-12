from __future__ import annotations

import asyncio
import secrets
import string
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models
from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.common.models import TimeStampedModel

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class TransactionType(models.TextChoices):
    ORDER_PAYMENT = "order_payment", "Order Payment"
    ESCROW_HOLD = "escrow_hold", "Escrow Hold"
    ESCROW_RELEASE = "escrow_release", "Escrow Release"
    COMMISSION = "commission", "Commission"
    MEASUREMENT_FEE = "measurement_fee", "Measurement Fee"
    VENDOR_SUBSCRIPTION = "vendor_subscription", "Vendor Subscription"
    PLATFORM_USAGE_FEE = "platform_usage_fee", "Platform Usage Fee"
    ADVERTISEMENT_FEE = "advertisement_fee", "Advertisement Fee"
    AFFILIATE_REVENUE = "affiliate_revenue", "Affiliate Revenue"
    REFUND = "refund", "Refund"
    PAYOUT = "payout", "Payout"
    TRANSFER = "transfer", "Transfer"
    REVERSAL = "reversal", "Reversal"
    ADJUSTMENT = "adjustment", "Adjustment"


class TransactionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    REVERSED = "reversed", "Reversed"
    DISPUTED = "disputed", "Disputed"


class TransactionDirection(models.TextChoices):
    INBOUND = "inbound", "Inbound"
    OUTBOUND = "outbound", "Outbound"
    INTERNAL = "internal", "Internal"


class RevenueCategory(models.TextChoices):
    ORDER_COMMISSION = "order_commission", "Order Commission"
    MEASUREMENT_SERVICE = "measurement_service", "Measurement Service"
    VENDOR_SERVICE = "vendor_service", "Vendor Service"
    ADVERTISING = "advertising", "Advertising"
    AFFILIATE = "affiliate", "Affiliate"
    ADJUSTMENT = "adjustment", "Adjustment"


class Transaction(TimeStampedModel):
    transaction_type = models.CharField(max_length=40, choices=TransactionType.choices, db_index=True)
    status = models.CharField(max_length=30, choices=TransactionStatus.choices, default=TransactionStatus.PENDING, db_index=True)
    direction = models.CharField(max_length=20, choices=TransactionDirection.choices, default=TransactionDirection.INTERNAL, db_index=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    net_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="financial_transactions_sent", null=True, blank=True)
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="financial_transactions_received", null=True, blank=True)
    from_wallet = models.ForeignKey("wallet.Wallet", on_delete=models.SET_NULL, related_name="debit_transactions", null=True, blank=True)
    to_wallet = models.ForeignKey("wallet.Wallet", on_delete=models.SET_NULL, related_name="credit_transactions", null=True, blank=True)
    reference = models.CharField(max_length=120, unique=True, db_index=True)
    external_reference = models.CharField(max_length=160, blank=True, default="", db_index=True)
    provider_reference = models.CharField(max_length=160, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(max_length=160, blank=True, default="", db_index=True)
    order_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    measurement_request_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    description = models.CharField(max_length=500, blank=True, default="")
    from_balance_before = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    from_balance_after = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    to_balance_before = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    to_balance_after = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    initiated_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=500, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["from_user", "-created_at"]),
            models.Index(fields=["to_user", "-created_at"]),
            models.Index(fields=["transaction_type", "status"]),
            models.Index(fields=["order_id", "transaction_type"]),
            models.Index(fields=["idempotency_key"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["transaction_type", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_transaction_type_idempotency_key",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.generate_reference()
        if self.net_amount == Decimal("0.00"):
            self.net_amount = self.amount - self.fee_amount
        super().save(*args, **kwargs)

    @staticmethod
    def generate_reference(prefix: str = "FST") -> str:
        chars = string.ascii_uppercase + string.digits
        return f"{prefix}{''.join(secrets.choice(chars) for _ in range(25))}"

    def complete(self):
        self.status = TransactionStatus.COMPLETED
        self.completed_at = timezone.now()
        self.processed_at = self.processed_at or self.completed_at

    # ------------------------------------------------------------------
    # DATABASE-LEVEL SYNC CLASSMETHODS (DRF / Admin)
    # ------------------------------------------------------------------

    @classmethod
    def get_user_summary(cls, user: "AbstractUser") -> dict[str, Any]:
        """Single-pass aggregate: inflow, outflow, net, count via DB reverse FK.

        Traversal: user.financial_transactions_sent + user.financial_transactions_received

        Args:
            user: Authenticated Django user.

        Returns:
            dict with inflow, outflow, net (all as str), count as int.
        """
        received_agg = cls.objects.filter(
            to_user=user,
            status=TransactionStatus.COMPLETED,
        ).aggregate(
            total=Coalesce(Sum("net_amount"), Decimal("0.00"), output_field=DecimalField()),
            count=Count("id"),
        )
        sent_agg = cls.objects.filter(
            from_user=user,
            status=TransactionStatus.COMPLETED,
        ).aggregate(
            total=Coalesce(Sum("net_amount"), Decimal("0.00"), output_field=DecimalField()),
        )
        inflow = received_agg["total"]
        outflow = sent_agg["total"]
        return {
            "inflow": str(inflow),
            "outflow": str(outflow),
            "net": str(inflow - outflow),
            "count": received_agg["count"],
        }

    @classmethod
    def get_status_breakdown(cls, user: "AbstractUser") -> dict[str, int]:
        """Status count breakdown for a user's transactions (both sent and received).

        Args:
            user: Authenticated Django user.

        Returns:
            dict mapping each TransactionStatus to count.
        """
        qs = cls.objects.filter(Q(from_user=user) | Q(to_user=user))
        rows = qs.values("status").annotate(cnt=Count("id"))
        return {row["status"]: row["cnt"] for row in rows}

    @classmethod
    def get_recent_for_user(cls, user: "AbstractUser", limit: int = 10) -> list[dict]:
        """Most recent transactions for a user in a single query.

        Traversal: user.financial_transactions_sent | user.financial_transactions_received

        Args:
            user: Authenticated Django user.
            limit: Max rows (default 10).

        Returns:
            list[dict] of transaction rows ordered by -created_at.
        """
        qs = (
            cls.objects.filter(Q(from_user=user) | Q(to_user=user))
            .order_by("-created_at")[:limit]
            .values(
                "id", "reference", "transaction_type", "status", "direction",
                "amount", "fee_amount", "net_amount", "description",
                "order_id", "created_at",
            )
        )
        return list(qs)

    # ------------------------------------------------------------------
    # DATABASE-LEVEL ASYNC CLASSMETHODS (Ninja endpoints)
    # ------------------------------------------------------------------

    @classmethod
    async def aget_user_summary(cls, user: "AbstractUser") -> dict[str, Any]:
        """Async single-pass inflow/outflow aggregate.

        Args:
            user: Authenticated Django user.

        Returns:
            dict with inflow, outflow, net (str), count (int).
        """
        received_task = cls.objects.filter(
            to_user=user,
            status=TransactionStatus.COMPLETED,
        ).aaggregate(
            total=Coalesce(Sum("net_amount"), Decimal("0.00"), output_field=DecimalField()),
            count=Count("id"),
        )
        sent_task = cls.objects.filter(
            from_user=user,
            status=TransactionStatus.COMPLETED,
        ).aaggregate(
            total=Coalesce(Sum("net_amount"), Decimal("0.00"), output_field=DecimalField()),
        )
        received_agg, sent_agg = await asyncio.gather(received_task, sent_task)
        inflow = received_agg["total"]
        outflow = sent_agg["total"]
        return {
            "inflow": str(inflow),
            "outflow": str(outflow),
            "net": str(inflow - outflow),
            "count": received_agg["count"],
        }

    @classmethod
    async def aget_status_breakdown(cls, user: "AbstractUser") -> dict[str, int]:
        """Async status breakdown count for user's transactions.

        Args:
            user: Authenticated Django user.

        Returns:
            dict mapping each status to count.
        """
        qs = cls.objects.filter(Q(from_user=user) | Q(to_user=user)).values("status").annotate(cnt=Count("id"))
        return {row["status"]: row["cnt"] async for row in qs}

    @classmethod
    async def aget_recent_for_user(cls, user: "AbstractUser", limit: int = 10) -> list[dict]:
        """Async most recent transactions for user.

        Traversal: user.financial_transactions_sent | user.financial_transactions_received

        Args:
            user: Authenticated Django user.
            limit: Max rows (default 10).

        Returns:
            list[dict] of transaction rows ordered by -created_at.
        """
        qs = (
            cls.objects.filter(Q(from_user=user) | Q(to_user=user))
            .order_by("-created_at")[:limit]
            .values(
                "id", "reference", "transaction_type", "status", "direction",
                "amount", "fee_amount", "net_amount", "description",
                "order_id", "created_at",
            )
        )
        return [row async for row in qs]

    @classmethod
    async def aget_full_dashboard_data(cls, user: "AbstractUser") -> dict[str, Any]:
        """Async full transaction dashboard: summary + breakdown + recent in 3 DB queries.

        Args:
            user: Authenticated Django user.

        Returns:
            dict with summary, status_breakdown, and recent_transactions.
        """
        summary, breakdown, recent = await asyncio.gather(
            cls.aget_user_summary(user),
            cls.aget_status_breakdown(user),
            cls.aget_recent_for_user(user, limit=5),
        )
        return {
            **summary,
            "status_breakdown": breakdown,
            "recent_transactions": [
                {
                    **row,
                    "id": str(row["id"]),
                    "amount": str(row["amount"]),
                    "fee_amount": str(row["fee_amount"]),
                    "net_amount": str(row["net_amount"]),
                    "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                }
                for row in recent
            ],
        }




class TransactionFee(TimeStampedModel):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="fees")
    fee_type = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    percentage = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    description = models.CharField(max_length=240, blank=True, default="")


class TransactionLog(TimeStampedModel):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="logs")
    previous_status = models.CharField(max_length=30, blank=True, default="")
    new_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.CharField(max_length=240, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]


class DisputeStatus(models.TextChoices):
    OPENED = "opened", "Opened"
    INVESTIGATING = "investigating", "Investigating"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class TransactionDispute(TimeStampedModel):
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.PROTECT,  # PROTECT: dispute is a legal record — must not silently vanish
        related_name="disputes",
    )
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="financial_disputes")
    status = models.CharField(max_length=30, choices=DisputeStatus.choices, default=DisputeStatus.OPENED, db_index=True)
    reason = models.TextField()
    disputed_amount = models.DecimalField(max_digits=20, decimal_places=2)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="resolved_financial_disputes", null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, default="")
    evidence = models.JSONField(default=dict, blank=True)


class TransactionIdempotencyKey(TimeStampedModel):
    key = models.CharField(max_length=160, unique=True, db_index=True)
    request_hash = models.CharField(max_length=128, blank=True, default="")
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, related_name="idempotency_records", null=True, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)


class CommissionRule(TimeStampedModel):
    vendor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,  # SET_NULL: commission rule survives vendor account deletion (financial audit)
        related_name="commission_rules",
        null=True,
        blank=True,
    )
    rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.1000"))
    min_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.0500"))
    max_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.1000"))
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["vendor_user", "is_active"])]

    def clean(self):
        if self.rate < self.min_rate or self.rate > self.max_rate:
            from django.core.exceptions import ValidationError
            raise ValidationError("Commission rate must stay within the configured min/max range.")


class CompanyRevenueEntry(TimeStampedModel):
    transaction = models.OneToOneField(Transaction, on_delete=models.PROTECT, related_name="company_revenue")
    category = models.CharField(max_length=40, choices=RevenueCategory.choices, db_index=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.ForeignKey("wallet.Currency", on_delete=models.PROTECT)
    source_reference = models.CharField(max_length=160, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["category", "-created_at"])]
