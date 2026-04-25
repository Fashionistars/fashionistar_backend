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
