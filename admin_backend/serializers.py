from rest_framework import serializers
from .models import Collections
from .models import Category, Brand

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



