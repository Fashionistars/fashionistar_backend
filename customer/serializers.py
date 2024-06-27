from rest_framework import serializers
from .models import DeliveryContact, ShippingAddress

# models
from userauths.models import Profile




class SetTransactionPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=4, min_length=4, write_only=True)
    confirm_password = serializers.CharField(max_length=4, min_length=4, write_only=True)

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def save(self, user):
        profile = Profile.objects.get(user=user)
        profile.set_transaction_password(self.validated_data['password'])


class ValidateTransactionPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=4, min_length=4, write_only=True)


class DeliveryContactSerializer(serializers.ModelSerializer):
    """
    Serializer for the DeliveryContact model.
    """
    class Meta:
        model = DeliveryContact
        fields = '__all__'

class ShippingAddressSerializer(serializers.ModelSerializer):
    """
    Serializer for the ShippingAddress model.
    """
    class Meta:
        model = ShippingAddress
        fields = '__all__'
