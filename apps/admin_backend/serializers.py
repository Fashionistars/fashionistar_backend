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


