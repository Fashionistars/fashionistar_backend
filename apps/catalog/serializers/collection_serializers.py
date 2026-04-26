from rest_framework import serializers

from apps.catalog.models import Collections
from apps.catalog.serializers.common import safe_media_url


class CatalogCollectionSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="title", read_only=True)
    image_url = serializers.SerializerMethodField()
    background_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Collections
        fields = (
            "id",
            "name",
            "title",
            "slug",
            "sub_title",
            "description",
            "image",
            "image_url",
            "cloudinary_url",
            "background_image",
            "background_image_url",
            "background_cloudinary_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "image_url",
            "background_image_url",
            "created_at",
            "updated_at",
        )

    def get_image_url(self, obj) -> str:
        return safe_media_url(obj, "cloudinary_url", "image")

    def get_background_image_url(self, obj) -> str:
        return safe_media_url(obj, "background_cloudinary_url", "background_image")

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Collection title must be at least 2 characters.")
        return value
