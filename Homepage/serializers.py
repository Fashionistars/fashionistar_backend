from rest_framework import serializers
from .models import Collections, Category, Brand

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
