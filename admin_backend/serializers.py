from rest_framework import serializers
from .models import Collections
from .models import Category, Brand
from chat.models import Message



class MessageViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = '__all__'
        read_only_fields = ['sender', 'recipient', 'message', 'files', 'timestamp']


class CollectionsSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Collections
        fields = ['id', 'background_image', 'image']
        


# Define a serializer for the Category model
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


# Define a serializer for the Brand model
class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'


class AdminProfitSerializer(serializers.Serializer):
    profit = serializers.DecimalField(max_digits=10, decimal_places=2)


