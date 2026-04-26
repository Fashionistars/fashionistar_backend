# apps/admin_backend/serializers.py
from rest_framework import serializers
from apps.admin_backend.models import Brand, Category, Collections



class CollectionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collections
        fields = '__all__'
        read_only_fields = ['slug', 'created_at', 'updated_at']

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ['slug', 'created_at', 'updated_at']

class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'
        read_only_fields = ['slug', 'created_at', 'updated_at']


class AdminProfitSerializer(serializers.Serializer):
    profit = serializers.DecimalField(max_digits=10, decimal_places=2)


class DeliveryStatusUpdateSerializer(serializers.Serializer):
    delivery_status = serializers.CharField(max_length=100, required=False)
    tracking_id = serializers.CharField(max_length=255, required=False)

    def validate_delivery_status(self, value):
        valid_statuses = ['pending', 'shipping', 'delivered', 'cancelled']
        if value and value.lower() not in valid_statuses:
            raise serializers.ValidationError(f"Invalid delivery status. Must be one of: {', '.join(valid_statuses)}")
        return value.lower()


