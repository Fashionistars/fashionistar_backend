from django.utils import timezone

from apps.catalog.models import BlogPost, BlogPostStatus, Brand, Category, Collections
from apps.common.selectors import BaseSelector


class CatalogSelector(BaseSelector):
    """Read-side query helpers for public commerce metadata."""

    @staticmethod
    def categories():
        return (
            Category.objects.filter(active=True)
            .only("id", "name", "slug", "image", "active", "created_at", "updated_at")
            .order_by("name")
        )

    @staticmethod
    def brands():
        return (
            Brand.objects.filter(active=True)
            .only("id", "title", "slug", "description", "image", "active", "created_at", "updated_at")
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
                "background_image",
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

    @staticmethod
    def category_by_slug(slug: str):
        """Return one active category by slug or None."""

        try:
            return CatalogSelector.categories().get(slug=slug)
        except Category.DoesNotExist:
            return None

    @staticmethod
    def brand_by_slug(slug: str):
        """Return one active brand by slug or None."""

        try:
            return CatalogSelector.brands().get(slug=slug)
        except Brand.DoesNotExist:
            return None

    @staticmethod
    def collection_by_slug(slug: str):
        """Return one collection by slug or None."""

        try:
            return CatalogSelector.collections().get(slug=slug)
        except Collections.DoesNotExist:
            return None

    @staticmethod
    def blog_post_by_slug(slug: str, *, include_drafts: bool = False):
        """Return one visible blog post by slug or None."""

        try:
            return CatalogSelector.blog_posts(include_drafts=include_drafts).get(slug=slug)
        except BlogPost.DoesNotExist:
            return None

    @staticmethod
    def acategories():
        """Async-ready active category queryset."""

        return CatalogSelector.categories()

    @staticmethod
    def abrands():
        """Async-ready active brand queryset."""

        return CatalogSelector.brands()

    @staticmethod
    def acollections():
        """Async-ready collection queryset."""

        return CatalogSelector.collections()

    @staticmethod
    def ablog_posts(*, include_drafts: bool = False):
        """Async-ready published blog queryset."""

        return CatalogSelector.blog_posts(include_drafts=include_drafts)

    @staticmethod
    async def acategory_by_slug(slug: str):
        """Async: return one active category by slug or None."""

        try:
            return await CatalogSelector.acategories().aget(slug=slug)
        except Category.DoesNotExist:
            return None

    @staticmethod
    async def abrand_by_slug(slug: str):
        """Async: return one active brand by slug or None."""

        try:
            return await CatalogSelector.abrands().aget(slug=slug)
        except Brand.DoesNotExist:
            return None

    @staticmethod
    async def acollection_by_slug(slug: str):
        """Async: return one collection by slug or None."""

        try:
            return await CatalogSelector.acollections().aget(slug=slug)
        except Collections.DoesNotExist:
            return None

    @staticmethod
    async def ablog_post_by_slug(slug: str, *, include_drafts: bool = False):
        """Async: return one visible blog post by slug or None."""

        try:
            return await CatalogSelector.ablog_posts(include_drafts=include_drafts).aget(slug=slug)
        except BlogPost.DoesNotExist:
            return None
