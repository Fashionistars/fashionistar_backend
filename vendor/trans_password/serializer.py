from rest_framework import serializers
from vendor.models import Vendor
import logging

application_logger = logging.getLogger('application')

class SetTransactionPasswordSerializer(serializers.Serializer):
    """
    Serializer for setting the transaction password for a Vendor.

    This serializer is responsible for validating and setting the transaction
    password for a vendor.  The password must be a 4-digit numeric string.

    Fields:
        password (CharField): The new transaction password (write-only).  MUST be a 4-digit number.
        confirm_password (CharField): The confirmation of the new transaction password (write-only). MUST be a 4-digit number.

    Methods:
        validate(data): Validates that the password and confirmation match and that the password meets complexity requirements.
        save(user): Sets the validated transaction password for the associated vendor.
    """

    password = serializers.CharField(max_length=4, min_length=4, write_only=True, help_text="Must be a 4-digit number.")
    confirm_password = serializers.CharField(max_length=4, min_length=4, write_only=True, help_text="Must be a 4-digit number.")

    def validate(self, data):
        """
        Validates that the password and confirmation match and that the password is a valid 4-digit number.

        Args:
            data (dict): The input data containing the password and confirmation.

        Returns:
            dict: The validated data.

        Raises:
            serializers.ValidationError: If the passwords don't match, or the password doesn't meet the numeric and length requirements.
        """
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        # Ensure that password and confirm password are equal
        if password != confirm_password:
            raise serializers.ValidationError("Passwords do not match.")

        # Ensure that the password consist of only digits
        if not password.isdigit():
            raise serializers.ValidationError("Transaction password must contain only digits.")

        # Ensure that the password length is exactly 4
        if len(password) != 4:
            raise serializers.ValidationError("Transaction password must be exactly 4 digits.")

        return data

    def save(self, user):
        """
        Sets the validated transaction password for the associated vendor.

        Args:
            user (User): The user for whom to set the transaction password.

        Returns:
            Vendor: The vendor object with the updated transaction password.

        Raises:
            serializers.ValidationError: If no vendor profile is found for this user.
        """
        try:
            vendor = Vendor.objects.get(user=user)
            vendor.set_transaction_password(self.validated_data['password'])
            return vendor
        except Vendor.DoesNotExist:
            raise serializers.ValidationError("Vendor profile not found for this user.")





            