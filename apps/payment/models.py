from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models
from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce

from apps.common.models import TimeStampedModel

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class PaymentProviderCode(models.TextChoices):
    PAYSTACK = "paystack", "Paystack"
    FLUTTERWAVE = "flutterwave", "flutterwave"
    STRIPE = "stripe", "stripe"
    PAYPAL = "paypal", "paypal"
    CASH = "cash", "cash"
    BANK_TRANSFER = "bank_transfer", "bank_transfer"
    USSD = "ussd", "ussd"
    QR = "qr", "qr"
    WALLET = "wallet", "wallet"
    CARD = "card", "card"
    GIFT_CARD = "gift_card", "gift_card"
    BANK_DEPOSIT = "bank_deposit", "bank_deposit"
    VOUCHER = "voucher", "voucher"
    APP = "app", "app"
    COD = "cod", "cod"
    OTHERS = "others", "others"
    OLIVE_PAY = "olive_pay", "olive_pay"


class PaymentIntentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    INITIALIZED = "initialized", "Initialized"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class PaymentPurpose(models.TextChoices):
    WALLET_TOPUP = "wallet_topup", "Wallet Top-up"
    ORDER_PAYMENT = "order_payment", "Order Payment"
    MEASUREMENT_FEE = "measurement_fee", "Measurement Fee"
    VENDOR_SERVICE = "vendor_service", "Vendor Service"
    ADVERTISEMENT_FEE = "advertisement_fee", "Advertisement Fee"


class PaymentProvider(TimeStampedModel):
    code = models.CharField(
        max_length=40, choices=PaymentProviderCode.choices, unique=True
    )
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.name


class PaymentIntent(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payment_intents",
    )
    provider = models.CharField(
        max_length=40,
        choices=PaymentProviderCode.choices,
        default=PaymentProviderCode.PAYSTACK,
        db_index=True,
    )
    purpose = models.CharField(
        max_length=40, choices=PaymentPurpose.choices, db_index=True
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=10, default="NGN")
    status = models.CharField(
        max_length=30,
        choices=PaymentIntentStatus.choices,
        default=PaymentIntentStatus.PENDING,
        db_index=True,
    )
    reference = models.CharField(max_length=120, unique=True, db_index=True)
    provider_reference = models.CharField(
        max_length=160, blank=True, default="", db_index=True
    )
    authorization_url = models.URLField(max_length=1000, blank=True, default="")
    access_code = models.CharField(max_length=160, blank=True, default="")
    order_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    measurement_request_id = models.CharField(
        max_length=120, blank=True, default="", db_index=True
    )
    idempotency_key = models.CharField(
        max_length=160, blank=True, default="", db_index=True
    )
    provider_response = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["purpose", "status"]),
        ]

    # ------------------------------------------------------------------
    # DATABASE-LEVEL SYNC CLASSMETHODS (DRF / Admin use)
    # ------------------------------------------------------------------

    @classmethod
    def get_recent_for_user(cls, user: "AbstractUser", limit: int = 10) -> list[dict]:
        """Recent payment intents for user as a list of dicts.

        Traversal: user.payment_intents reverse FK

        Args:
            user: Authenticated Django user.
            limit: Max intents to return.

        Returns:
            list[dict] of intent rows ordered by -created_at.
        """
        return list(
            cls.objects.filter(user=user)
            .order_by("-created_at")[:limit]
            .values(
                "id",
                "provider",
                "purpose",
                "amount",
                "currency",
                "status",
                "reference",
                "created_at",
            )
        )

    @classmethod
    def get_summary_for_user(cls, user: "AbstractUser") -> dict[str, Any]:
        """Aggregate intent stats: pending count, succeeded total, total intent count.

        Traversal: user.payment_intents

        Args:
            user: Authenticated Django user.

        Returns:
            dict with pending_count, succeeded_total, total_count.
        """
        agg = cls.objects.filter(user=user).aggregate(
            total_count=Count("id"),
            pending_count=Count("id", filter=Q(status=PaymentIntentStatus.PENDING)),
            succeeded_total=Coalesce(
                Sum("amount", filter=Q(status=PaymentIntentStatus.SUCCEEDED)),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
        )
        return {
            "total_count": agg["total_count"],
            "pending_count": agg["pending_count"],
            "succeeded_total": str(agg["succeeded_total"]),
        }

    # ------------------------------------------------------------------
    # DATABASE-LEVEL ASYNC CLASSMETHODS (Ninja endpoints)
    # ------------------------------------------------------------------

    @classmethod
    async def aget_recent_for_user(
        cls, user: "AbstractUser", limit: int = 10
    ) -> list[dict]:
        """Async recent payment intents for user.

        Traversal: user.payment_intents reverse FK

        Args:
            user: Authenticated Django user.
            limit: Max intents to return.

        Returns:
            list[dict] of intent rows ordered by -created_at.
        """
        qs = (
            cls.objects.filter(user=user)
            .order_by("-created_at")[:limit]
            .values(
                "id",
                "provider",
                "purpose",
                "amount",
                "currency",
                "status",
                "reference",
                "created_at",
            )
        )
        return [row async for row in qs]

    @classmethod
    async def aget_summary_for_user(cls, user: "AbstractUser") -> dict[str, Any]:
        """Async aggregate intent stats for user.

        Traversal: user.payment_intents

        Args:
            user: Authenticated Django user.

        Returns:
            dict with pending_count, succeeded_total, total_count.
        """
        agg = await cls.objects.filter(user=user).aaggregate(
            total_count=Count("id"),
            pending_count=Count("id", filter=Q(status=PaymentIntentStatus.PENDING)),
            succeeded_total=Coalesce(
                Sum("amount", filter=Q(status=PaymentIntentStatus.SUCCEEDED)),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
        )
        return {
            "total_count": agg["total_count"],
            "pending_count": agg["pending_count"],
            "succeeded_total": str(agg["succeeded_total"]),
        }

    @classmethod
    async def aget_full_dashboard_data(cls, user: "AbstractUser") -> dict[str, Any]:
        """Async full payment dashboard: summary + recent intents in 2 DB queries.

        Args:
            user: Authenticated Django user.

        Returns:
            dict combining summary and recent payment intents.
        """
        summary = await cls.aget_summary_for_user(user)
        recent = await cls.aget_recent_for_user(user, limit=5)
        return {
            **summary,
            "recent_intents": [
                {
                    **row,
                    "id": str(row["id"]),
                    "amount": str(row["amount"]),
                    "created_at": (
                        row["created_at"].isoformat() if row.get("created_at") else None
                    ),
                }
                for row in recent
            ],
        }


class PaymentWebhookEvent(TimeStampedModel):
    provider = models.CharField(
        max_length=40, choices=PaymentProviderCode.choices, db_index=True
    )
    event = models.CharField(max_length=120, db_index=True)
    event_id = models.CharField(max_length=160, blank=True, default="", db_index=True)
    reference = models.CharField(max_length=160, blank=True, default="", db_index=True)
    payload_hash = models.CharField(max_length=128, unique=True)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False, db_index=True)
    processing_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["provider", "event", "processed"])]


class PaystackTransferRecipient(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="paystack_transfer_recipients",
    )
    recipient_code = models.CharField(max_length=160, unique=True, db_index=True)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=180)
    bank_name = models.CharField(max_length=180)
    bank_code = models.CharField(max_length=20)
    provider_response = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)


class PaymentProviderLog(TimeStampedModel):
    provider = models.CharField(
        max_length=40, choices=PaymentProviderCode.choices, db_index=True
    )
    action = models.CharField(max_length=120, db_index=True)
    reference = models.CharField(max_length=160, blank=True, default="", db_index=True)
    success = models.BooleanField(default=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
