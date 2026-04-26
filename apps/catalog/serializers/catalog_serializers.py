from rest_framework import serializers

from apps.admin_backend.models import Brand, Category, Collections


def _safe_media_url(obj, *field_names: str) -> str:
    for field_name in field_names:
        value = getattr(obj, field_name, None)
        if not value:
            continue
        if isinstance(value, str):
            return value
        try:
            url = value.url
        except (ValueError, AttributeError):
            continue
        if url:
            return url
    return ""


class CatalogCategorySerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="name", read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "title",
            "slug",
            "image",
            "image_url",
            "cloudinary_url",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("slug", "image_url", "created_at", "updated_at")

    def get_image_url(self, obj) -> str:
        return _safe_media_url(obj, "cloudinary_url", "image")

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Category name must be at least 2 characters.")
        return value


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
            "image_url",
            "cloudinary_url",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("slug", "image_url", "created_at", "updated_at")

    def get_image_url(self, obj) -> str:
        return _safe_media_url(obj, "cloudinary_url", "image")

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Brand title must be at least 2 characters.")
        return value


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
            "slug",
            "image_url",
            "background_image_url",
            "created_at",
            "updated_at",
        )

    def get_image_url(self, obj) -> str:
        return _safe_media_url(obj, "cloudinary_url", "image")

    def get_background_image_url(self, obj) -> str:
        return _safe_media_url(obj, "background_cloudinary_url", "background_image")

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Collection title must be at least 2 characters.")
        return value
