# apps/product/serializers/review_serializers.py
from rest_framework import serializers
from apps.product.models import ProductReview


class ProductReviewSerializer(serializers.ModelSerializer):
    reviewer_display = serializers.SerializerMethodField()

    class Meta:
        model = ProductReview
        fields = [
            "id", "rating", "review", "reply",
            "reviewer_display", "helpful_votes",
            "active", "moderated", "created_at",
        ]
        read_only_fields = ["reply", "helpful_votes", "active", "moderated", "created_at"]

    def get_reviewer_display(self, obj):
        if obj.reviewer_name:
            return obj.reviewer_name
        return "Anonymous"


class ProductReviewWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductReview
        fields = ["rating", "review"]

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value
