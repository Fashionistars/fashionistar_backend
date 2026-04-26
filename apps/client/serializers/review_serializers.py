from rest_framework import serializers


class ClientReviewSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    user = serializers.CharField(read_only=True)
    user_full_name = serializers.CharField(source="user.full_name", read_only=True)
    user_avatar = serializers.CharField(source="user.profile.image", read_only=True)
    product = serializers.CharField(read_only=True)
    product_id = serializers.UUIDField(write_only=True, required=False)
    product_title = serializers.CharField(source="product.title", read_only=True)
    review = serializers.CharField(max_length=2000)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    active = serializers.BooleanField(read_only=True)
    date = serializers.DateTimeField(read_only=True)
