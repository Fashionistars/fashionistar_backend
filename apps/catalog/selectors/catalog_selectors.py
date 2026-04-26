from django.utils import timezone

from apps.catalog.models import BlogPost, BlogPostStatus, Brand, Category, Collections


class CatalogSelector:
    """Read-side query helpers for public commerce metadata."""

    @staticmethod
    def categories():
        return (
            Category.objects.filter(active=True)
            .only("id", "name", "slug", "image", "cloudinary_url", "active", "created_at", "updated_at")
            .order_by("name")
        )

    @staticmethod
    def brands():
        return (
            Brand.objects.filter(active=True)
            .only("id", "title", "slug", "description", "image", "cloudinary_url", "active", "created_at", "updated_at")
            .order_by("title")
        )

    @staticmethod
    def collections():
        return (
            Collections.objects.all()
            .only(
                "id",
                "title",
                "slug",
                "sub_title",
                "description",
                "image",
                "cloudinary_url",
                "background_image",
                "background_cloudinary_url",
                "created_at",
                "updated_at",
            )
            .order_by("-created_at")
        )

    @staticmethod
    def blog_posts(*, include_drafts: bool = False):
        queryset = (
            BlogPost.objects.select_related("author", "category")
            .prefetch_related("gallery_media")
            .only(
                "id",
                "author",
                "category",
                "title",
                "slug",
                "excerpt",
                "content",
                "featured_image",
                "featured_image_cloudinary_url",
                "status",
                "tags",
                "seo_title",
                "seo_description",
                "is_featured",
                "published_at",
                "view_count",
                "created_at",
                "updated_at",
            )
        )
        if include_drafts:
            return queryset.order_by("-updated_at")
        return queryset.filter(
            status=BlogPostStatus.PUBLISHED,
            published_at__lte=timezone.now(),
            is_deleted=False,
        ).order_by("-is_featured", "-published_at", "-created_at")
