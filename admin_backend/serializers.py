from rest_framework import serializers
from admin_backend.models import Collections
from admin_backend.models import Category, Brand
from chat.models import Message



class MessageViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = '__all__'
        read_only_fields = ['sender', 'recipient', 'message', 'files', 'timestamp']



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


