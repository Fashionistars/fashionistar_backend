from decimal import Decimal

from rest_framework import serializers

from apps.wallet.models import Wallet, WalletHold


class WalletSerializer(serializers.ModelSerializer):
    currency = serializers.CharField(source="currency.code")
    has_pin = serializers.BooleanField(read_only=True)

    class Meta:
        model = Wallet
        fields = [
            "id", "owner_type", "name", "currency", "balance", "available_balance",
            "pending_balance", "escrow_balance", "status", "has_pin",
            "daily_limit", "monthly_limit", "last_transaction_at",
        ]


class WalletPinSetSerializer(serializers.Serializer):
    pin = serializers.RegexField(regex=r"^\d{4}$", max_length=4, min_length=4)


class WalletPinChangeSerializer(serializers.Serializer):
    current_pin = serializers.RegexField(regex=r"^\d{4}$", max_length=4, min_length=4)
    new_pin = serializers.RegexField(regex=r"^\d{4}$", max_length=4, min_length=4)


class WalletPinVerifySerializer(serializers.Serializer):
    pin = serializers.RegexField(regex=r"^\d{4}$", max_length=4, min_length=4)


class EscrowHoldSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    reference = serializers.CharField(max_length=120)
    order_id = serializers.CharField(max_length=120, required=False, allow_blank=True)
    provider_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)


class EscrowReleaseSerializer(serializers.Serializer):
    hold_reference = serializers.CharField(max_length=120)
    vendor_user_id = serializers.UUIDField(required=False)
    commission_rate = serializers.DecimalField(
        max_digits=5,
        decimal_places=4,
        required=False,
        default=Decimal("0.10"),
        min_value=Decimal("0.00"),
    )


class EscrowRefundSerializer(serializers.Serializer):
    hold_reference = serializers.CharField(max_length=120)


class WalletHoldSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletHold
        fields = ["id", "amount", "released_amount", "refunded_amount", "reference", "order_id", "status", "created_at"]


class WalletTransferSerializer(serializers.Serializer):
    """
    Serializer for P2P fund transfers.
    Validates receiver existence, positive amount, and PIN format.
    """
    receiver_id = serializers.UUIDField(help_text="ID of the user receiving the funds.")
    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="Amount to transfer (min 0.01).",
    )
    transaction_password = serializers.CharField(
        min_length=4,
        max_length=10,
        help_text="4-digit transaction PIN for authorization.",
    )


class WalletWithdrawalSerializer(serializers.Serializer):
    """Validate KYC-gated wallet withdrawal requests."""

    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    pin = serializers.RegexField(regex=r"^\d{4}$", max_length=4, min_length=4)
    bank_code = serializers.CharField(max_length=20)
    account_number = serializers.RegexField(regex=r"^\d{10}$", max_length=10, min_length=10)
    account_name = serializers.CharField(max_length=160)


class WalletWithdrawalResponseSerializer(serializers.Serializer):
    transaction_id = serializers.CharField()
    reference = serializers.CharField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    available_balance = serializers.DecimalField(max_digits=20, decimal_places=2)
    pending_balance = serializers.DecimalField(max_digits=20, decimal_places=2)


class WalletPinVerifyResponseSerializer(serializers.Serializer):
    valid = serializers.BooleanField()


class EscrowReleaseResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    released_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    fee_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    net_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    reference = serializers.CharField()
