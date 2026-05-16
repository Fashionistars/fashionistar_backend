from decimal import Decimal

from rest_framework import serializers

from apps.order.models import CashPaymentMode, OrderPaymentPath
from apps.payment.models import (
    PaymentIntent,
    PaymentProviderCode,
    PaymentPurpose,
    PaystackTransferRecipient,
)


class PaystackInitializeSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    purpose = serializers.ChoiceField(choices=PaymentPurpose.choices)
    currency = serializers.CharField(max_length=10, default="NGN")
    order_id = serializers.CharField(max_length=120, required=False, allow_blank=True)
    measurement_request_id = serializers.CharField(max_length=120, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)


class PaymentIntentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = [
            "id", "provider", "purpose", "amount", "currency", "status", "reference",
            "provider_reference", "authorization_url", "access_code", "order_id",
            "measurement_request_id", "created_at", "provider_response",
        ]


class TransferRecipientCreateSerializer(serializers.Serializer):
    account_number = serializers.CharField(max_length=20)
    account_name = serializers.CharField(max_length=180)
    bank_name = serializers.CharField(max_length=180)
    bank_code = serializers.CharField(max_length=20)


class PaystackTransferRecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaystackTransferRecipient
        fields = ["id", "recipient_code", "account_number", "account_name", "bank_name", "bank_code", "is_active", "created_at"]


class PaystackVerifySerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=120)


class PaystackBankSerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.CharField()
    code = serializers.CharField()
    longcode = serializers.CharField(required=False, allow_null=True)
    gateway = serializers.CharField(required=False, allow_null=True)
    pay_with_bank = serializers.BooleanField()
    active = serializers.BooleanField()
    is_deleted = serializers.BooleanField(required=False, allow_null=True)
    country = serializers.CharField()
    currency = serializers.CharField()
    type = serializers.CharField()
    id = serializers.IntegerField()
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class PaystackBanksResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
    data = PaystackBankSerializer(many=True)


class PaystackWebhookSerializer(serializers.Serializer):
    event = serializers.CharField()
    data = serializers.JSONField()


class WalletFundPaymentSerializer(serializers.Serializer):
    order_id = serializers.CharField(max_length=120, required=False, allow_blank=True)
    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
    )
    purpose = serializers.ChoiceField(choices=PaymentPurpose.choices)
    provider = serializers.ChoiceField(
        choices=[
            PaymentProviderCode.WALLET,
            PaymentProviderCode.PAYSTACK,
            PaymentProviderCode.FLUTTERWAVE,
            PaymentProviderCode.OLIVE_PAY,
        ]
    )
    currency = serializers.CharField(max_length=10, default="NGN")
    selected_percent = serializers.IntegerField(min_value=1, max_value=100, default=100)
    cash_payment_mode = serializers.ChoiceField(
        choices=CashPaymentMode.choices,
        default=CashPaymentMode.DISABLED,
    )
    payment_path = serializers.ChoiceField(
        choices=OrderPaymentPath.choices,
        default=OrderPaymentPath.GATEWAY,
    )
    metadata = serializers.JSONField(required=False, default=dict)


class CashConfirmationCreateSerializer(serializers.Serializer):
    order_id = serializers.CharField(max_length=120)


class CashConfirmationResendSerializer(serializers.Serializer):
    order_id = serializers.CharField(max_length=120)


class CashConfirmationConfirmSerializer(serializers.Serializer):
    order_id = serializers.CharField(max_length=120)
    client_token = serializers.CharField(max_length=255)
