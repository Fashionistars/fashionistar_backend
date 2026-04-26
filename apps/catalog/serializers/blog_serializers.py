from rest_framework import serializers

from apps.catalog.models import BlogMedia, BlogPost, BlogPostStatus
from apps.catalog.serializers.common import safe_media_url


class CatalogBlogMediaSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = BlogMedia
        fields = (
            "id",
            "image",
            "image_url",
            "cloudinary_url",
            "public_id",
            "alt_text",
            "sort_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "image_url", "created_at", "updated_at")

    def get_image_url(self, obj) -> str:
        return safe_media_url(obj, "cloudinary_url", "image")


class CatalogBlogPostSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True)
    author_name = serializers.SerializerMethodField()
    gallery_media = CatalogBlogMediaSerializer(many=True, read_only=True)

    class Meta:
        model = BlogPost
        fields = (
            "id",
            "author",
            "author_name",
            "category",
            "category_name",
            "title",
            "slug",
            "excerpt",
            "content",
            "featured_image",
            "featured_image_cloudinary_url",
            "image_url",
            "status",
            "tags",
            "seo_title",
            "seo_description",
            "is_featured",
            "published_at",
            "view_count",
            "gallery_media",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "author",
            "author_name",
            "slug",
            "image_url",
            "published_at",
            "view_count",
            "gallery_media",
            "created_at",
            "updated_at",
        )

    def get_image_url(self, obj) -> str:
        return obj.image_url

    def get_author_name(self, obj) -> str:
        author = getattr(obj, "author", None)
        if not author:
            return "Fashionistar Editorial"
        full_name = getattr(author, "get_full_name", lambda: "")()
        return full_name or getattr(author, "email", "") or str(author)

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError("Blog title must be at least 5 characters.")
        return value

    def validate_content(self, value: str) -> str:
        value = value.strip()
        if len(value) < 40:
            raise serializers.ValidationError("Blog content must be at least 40 characters.")
        return value

    def validate_tags(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Tags must be a list of strings.")
        normalized = [str(tag).strip().lower() for tag in value if str(tag).strip()]
        return normalized[:20]

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", None))
        if status == BlogPostStatus.PUBLISHED:
            excerpt = attrs.get("excerpt", getattr(self.instance, "excerpt", ""))
            seo_description = attrs.get(
                "seo_description",
                getattr(self.instance, "seo_description", ""),
            )
            if not excerpt:
                raise serializers.ValidationError({"excerpt": "Published blog posts need an excerpt."})
            if not seo_description:
                raise serializers.ValidationError(
                    {"seo_description": "Published blog posts need an SEO description."}
                )
        return attrs
