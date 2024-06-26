from rest_framework import serializers

# models
from .models import DeliveryContact, ShippingAddress



class DeliveryContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryContact
        fields = '__all__'

class ShippingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingAddress
        fields = '__all__'
