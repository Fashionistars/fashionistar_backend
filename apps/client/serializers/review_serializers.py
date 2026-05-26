from rest_framework import serializers

from apps.product.models import Product
from apps.product.services.product_service import create_review


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

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None:
            raise serializers.ValidationError("Authenticated user is required.")

        product_id = validated_data.pop("product_id", None)
        if product_id is None:
            raise serializers.ValidationError({"product_id": "This field is required."})

        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist as exc:
            raise serializers.ValidationError({"product_id": "Product not found."}) from exc

        request_meta = getattr(request, "META", {}) if request else {}

        try:
            return create_review(
                user=user,
                product=product,
                rating=validated_data["rating"],
                review_text=validated_data["review"],
                idempotency_key=request_meta.get("HTTP_X_IDEMPOTENCY_KEY"),
                request=request,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"review": str(exc)}) from exc
