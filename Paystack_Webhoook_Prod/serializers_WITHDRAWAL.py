from rest_framework import serializers
from decimal import Decimal


class VendorWithdrawSerializer(serializers.Serializer):
    """
     Serializer for the vendor withdraw endpoint.
    """
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'), required=True, help_text="The amount to withdraw from wallet balance.")
    transaction_password = serializers.CharField(required=True, help_text="The vendors transaction password.")
    bank_details_id = serializers.CharField(required=True, help_text="The id of the bank details to send the funds to.")
    reason = serializers.CharField(required=False, help_text="Reason for withdrawal")



    # =================  TO BE USED LATER FOR EFFICIENT SECURITY AND USER AMOUNT VALIDATION PLEASE ===================


    # amount = serializers.DecimalField(
    #     max_digits=12,
    #     decimal_places=2,
    #     min_value=Decimal('500.00'),  # Minimum withdrawal amount
    #     max_value=Decimal('1000000.00')
    # )
    # # ... other fields ...

    # def validate(self, data):
    #     if data['amount'] % Decimal('100.00') != 0:
    #         raise serializers.ValidationError("Withdrawal amount must be in multiples of 100")
    #     return data




