from rest_framework import serializers
from .models import Collections

class CollectionsSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Collections
        fields = ['id', 'background_image', 'image']
        


  