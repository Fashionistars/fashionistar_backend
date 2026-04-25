from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class PaymentProviderCode(models.TextChoices):
    PAYSTACK = "paystack", "Paystack"


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
    code = models.CharField(max_length=40, choices=PaymentProviderCode.choices, unique=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.name


class PaymentIntent(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payment_intents")
    provider = models.CharField(max_length=40, choices=PaymentProviderCode.choices, default=PaymentProviderCode.PAYSTACK, db_index=True)
    purpose = models.CharField(max_length=40, choices=PaymentPurpose.choices, db_index=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=10, default="NGN")
    status = models.CharField(max_length=30, choices=PaymentIntentStatus.choices, default=PaymentIntentStatus.PENDING, db_index=True)
    reference = models.CharField(max_length=120, unique=True, db_index=True)
    provider_reference = models.CharField(max_length=160, blank=True, default="", db_index=True)
    authorization_url = models.URLField(max_length=1000, blank=True, default="")
    access_code = models.CharField(max_length=160, blank=True, default="")
    order_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    measurement_request_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(max_length=160, blank=True, default="", db_index=True)
    provider_response = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["purpose", "status"]),
        ]


class PaymentWebhookEvent(TimeStampedModel):
    provider = models.CharField(max_length=40, choices=PaymentProviderCode.choices, db_index=True)
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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="paystack_transfer_recipients")
    recipient_code = models.CharField(max_length=160, unique=True, db_index=True)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=180)
    bank_name = models.CharField(max_length=180)
    bank_code = models.CharField(max_length=20)
    provider_response = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)


class PaymentProviderLog(TimeStampedModel):
    provider = models.CharField(max_length=40, choices=PaymentProviderCode.choices, db_index=True)
    action = models.CharField(max_length=120, db_index=True)
    reference = models.CharField(max_length=160, blank=True, default="", db_index=True)
    success = models.BooleanField(default=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
