from rest_framework import serializers
from store.models import Review, Product

class ClientReviewSerializer(serializers.ModelSerializer):
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    user_avatar = serializers.ImageField(source='user.profile.image', read_only=True)
    product_title = serializers.CharField(source='product.title', read_only=True)
    
    class Meta:
        model = Review
        fields = [
            'id', 'user', 'user_full_name', 'user_avatar', 
            'product', 'product_title', 'review', 'rating', 'active', 'date'
        ]
        read_only_fields = ['user', 'active', 'date']

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['user'] = request.user
        return super().create(validated_data)
