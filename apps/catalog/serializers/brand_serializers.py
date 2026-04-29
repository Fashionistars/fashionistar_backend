from rest_framework import serializers

from apps.catalog.models import Brand
from apps.catalog.serializers.common import safe_media_url


class CatalogBrandSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="title", read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = (
            "id",
            "name",
            "title",
            "slug",
            "description",
            "image",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "image_url", "created_at", "updated_at")

    def get_image_url(self, obj) -> str:
        return safe_media_url(obj, "image")

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Brand title must be at least 2 characters.")
        return value
