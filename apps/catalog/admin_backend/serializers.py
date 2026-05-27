# apps/catalog/admin_backend/serializers.py
from rest_framework import serializers
from apps.catalog.models.category import Category
from apps.catalog.models.brand import Brand
from apps.catalog.models.collection import Collections
from apps.catalog.models.blog import BlogPost

class AdminCategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "description", "active")
        read_only_fields = ("id",)

class AdminBrandWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "title", "description", "active")
        read_only_fields = ("id",)

class AdminCollectionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collections
        fields = ("id", "name", "description", "active")
        read_only_fields = ("id",)


class AdminBlogPostWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = (
            "id",
            "title",
            "slug",
            "excerpt",
            "content",
            "status",
            "tags",
            "is_featured",
            "published_at",
            "category",
        )
        read_only_fields = ("id", "slug")

