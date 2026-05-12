# apps/product/serializers/review_serializers.py
"""
Enterprise review serializers with reviewer snapshot, helpful-vote tracking,
vendor reply support, and idempotency key for safe client-side retry.
"""

from rest_framework import serializers
from apps.product.models import ProductReview


class ProductReviewSerializer(serializers.ModelSerializer):
    """Read serializer — returned on GET /products/:slug/reviews/."""
    reviewer_display = serializers.SerializerMethodField()
    reviewer_avatar_url = serializers.SerializerMethodField()
    product_title = serializers.CharField(source="product.title", read_only=True)

    class Meta:
        model = ProductReview
        fields = [
            "id",
            "product_title",
            "rating", "review",
            "reply",
            "reviewer_display", "reviewer_avatar_url",
            "helpful_votes",
            "active", "moderated",
            "created_at",
        ]
        read_only_fields = [
            "reply", "helpful_votes", "active", "moderated",
            "created_at", "product_title",
        ]

    def get_reviewer_display(self, obj):
        """Returns reviewer snapshot name, never the live FK — safe after user deletion."""
        if obj.reviewer_name:
            return obj.reviewer_name
        if obj.user:
            full = getattr(obj.user, "get_full_name", lambda: "")()
            return full or getattr(obj.user, "username", "Anonymous")
        return "Anonymous"

    def get_reviewer_avatar_url(self, obj):
        """Returns reviewer profile avatar if the user still exists."""
        if not obj.user:
            return None
        profile = getattr(obj.user, "profile", None)
        avatar = getattr(profile, "avatar", None) if profile else None
        return str(avatar.url) if avatar else None


class ProductReviewWriteSerializer(serializers.ModelSerializer):
    """
    Write serializer — used by clients on POST /products/:slug/reviews/.

    idempotency_key allows safe retry on network failure.
    The service layer checks it before inserting a new row.
    """
    idempotency_key = serializers.UUIDField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Client UUID — prevents duplicate review on network retry.",
    )

    class Meta:
        model = ProductReview
        fields = ["rating", "review", "idempotency_key"]

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_review(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError(
                "Review must be at least 10 characters long."
            )
        return value.strip()


class VendorReplySerializer(serializers.Serializer):
    """Used by vendor to post a reply to a review."""
    reply = serializers.CharField(
        min_length=5,
        max_length=2000,
        help_text="Vendor reply text shown publicly below the review.",
    )


class HelpfulVoteSerializer(serializers.Serializer):
    """Increment helpful_votes on a review (idempotent at client level)."""
    review_id = serializers.UUIDField()
