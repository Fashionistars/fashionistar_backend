from rest_framework import serializers
from .models import DeliveryContact, ShippingAddress

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
