from rest_framework import serializers


class VendorWithdrawSerializer(serializers.Serializer):
    """
     Serializer for the vendor withdraw endpoint.
    """
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01, required=True, help_text="The amount to withdraw from wallet balance.")
    transaction_password = serializers.CharField(required=True, help_text="The vendors transaction password.")
    bank_details_id = serializers.CharField(required=True, help_text="The id of the bank details to send the funds to.")
    reason = serializers.CharField(required=False, help_text="Reason for withdrawal")









    # IT IS STILL HAPPENING, CAN YOU TRY TO USE NORMAL APIVIEW TO HANDLE THIS PARTICULAR ENDPOINT TO CHECK IF IT IS FROM THE GENREIC FUNCTION?