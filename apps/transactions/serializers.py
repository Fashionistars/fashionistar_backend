from rest_framework import serializers

from apps.transactions.models import Transaction, TransactionDispute


class TransactionSerializer(serializers.ModelSerializer):
    from_wallet_currency = serializers.CharField(source="from_wallet.currency.code", read_only=True)
    to_wallet_currency = serializers.CharField(source="to_wallet.currency.code", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "transaction_type", "status", "direction", "amount", "fee_amount",
            "net_amount", "reference", "external_reference", "provider_reference",
            "order_id", "measurement_request_id", "description", "from_wallet_currency",
            "to_wallet_currency", "created_at", "completed_at", "metadata",
        ]


class DisputeCreateSerializer(serializers.Serializer):
    reason = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, min_value=0)


class TransactionDisputeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionDispute
        fields = ["id", "transaction", "status", "reason", "disputed_amount", "created_at"]


class RefundSerializer(serializers.Serializer):
    hold_reference = serializers.CharField(max_length=120)
