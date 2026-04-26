from rest_framework import serializers

from apps.payment.models import PaymentIntent, PaymentPurpose, PaystackTransferRecipient


class PaystackInitializeSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, min_value=0)
    purpose = serializers.ChoiceField(choices=PaymentPurpose.choices)
    currency = serializers.CharField(max_length=10, default="NGN")
    order_id = serializers.CharField(max_length=120, required=False, allow_blank=True)
    measurement_request_id = serializers.CharField(max_length=120, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)


class PaymentIntentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = [
            "id", "purpose", "amount", "currency", "status", "reference",
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
