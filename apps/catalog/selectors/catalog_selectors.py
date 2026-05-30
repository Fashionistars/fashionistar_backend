# apps/catalog/selectors/catalog_selectors.py
"""
Catalog Domain Selectors — Read-only data fetching layer.

Architecture Rules (NON-NEGOTIABLE):
  ─ Selectors NEVER mutate data. All mutations live in services/.
  ─ Sync selectors (no prefix)  → used in DRF sync views / admin.
  ─ Async selectors (prefix `a`) → used in Django-Ninja async views.
  ─ ZERO sync_to_async() usage.
  ─ All async selectors use Django 6.0 native async ORM:
      aget()          → single object lookup
      acount()        → COUNT aggregate
      aexists()       → EXISTS check
      afirst()        → first row or None
      [row async for] → async QuerySet iteration
  ─ Methods returning list[dict] use .values() + async iteration for
    maximum performance (no model instantiation overhead).

Reverse FK / related-name traversal map for this domain:
  category.catalog_categories (user FK reverse)
  collections.catalog_collections (user FK reverse)
  collections.vendor_collections → VendorProfile M2M reverse
  product.category               → Product FK to Category

Google-style docstrings required for all non-trivial functions.
"""

import logging
from typing import Any

from django.utils import timezone

from apps.catalog.models import BlogPost, BlogPostStatus, Brand, Category, Collections
from apps.common.selectors import BaseSelector

logger = logging.getLogger(__name__)


class CatalogSelector(BaseSelector):
    """Read-side query helpers for public commerce metadata."""

    # ══════════════════════════════════════════════════════════════════
    #  SYNC Queryset builders  (DRF / admin / SSR)
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def categories():
        """Return active categories queryset ordered by name."""
        return (
            Category.objects.filter(active=True)
            .only("id", "name", "slug", "image", "active", "created_at", "updated_at")
            .order_by("name")
        )

    @staticmethod
    def brands():
        """Return active brands queryset ordered by title."""
        return (
            Brand.objects.filter(active=True)
            .only("id", "title", "slug", "description", "image", "active", "created_at", "updated_at")
            .order_by("title")
        )

    @staticmethod
    def collections():
        """Return all collections queryset ordered by newest first."""
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
        """
        Return published blog posts queryset.

        Args:
            include_drafts: If True, return all statuses ordered by -updated_at.

        Returns:
            QuerySet[BlogPost] with author, category, gallery_media pre-loaded.
        """
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

    # ══════════════════════════════════════════════════════════════════
    #  SYNC list[dict] helpers  (values()-based — no model overhead)
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def get_categories_list() -> list[dict]:
        """
        Return all active categories as list[dict].

        Uses .values() to avoid model instantiation overhead.

        Returns:
            list[dict] with id, name, slug, active, created_at.
        """
        return list(
            Category.objects.filter(active=True)
            .values("id", "name", "slug", "active", "created_at")
            .order_by("name")
        )

    @staticmethod
    def get_collections_list() -> list[dict]:
        """
        Return all collections as list[dict].

        Returns:
            list[dict] with id, title, slug, sub_title, description, created_at.
        """
        return list(
            Collections.objects.values(
                "id", "title", "slug", "sub_title", "description", "created_at"
            ).order_by("-created_at")
        )

    @staticmethod
    def get_brands_list() -> list[dict]:
        """
        Return all active brands as list[dict].

        Returns:
            list[dict] with id, title, slug, description, active, created_at.
        """
        return list(
            Brand.objects.filter(active=True)
            .values("id", "title", "slug", "description", "active", "created_at")
            .order_by("title")
        )

    # ══════════════════════════════════════════════════════════════════
    #  ASYNC queryset builders  (thin wrappers for Ninja iteration)
    # ══════════════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════════════════════
    #  ASYNC single-object lookups
    # ══════════════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════════════════════
    #  ASYNC list[dict] selectors
    #  ── Only Django 6.0 native async ORM — ZERO sync_to_async ──
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    async def aget_categories_list() -> list[dict]:
        """
        Async: return all active categories as list[dict].

        Uses .values() + async iteration — ZERO sync_to_async.
        No model instantiation overhead.

        Returns:
            list[dict] with id, name, slug, active, created_at.
        """
        try:
            qs = (
                Category.objects.filter(active=True)
                .values("id", "name", "slug", "active", "created_at")
                .order_by("name")
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_categories_list: %s", exc)
            return []

    @staticmethod
    async def aget_collections_list() -> list[dict]:
        """
        Async: return all collections as list[dict].

        Uses .values() + async iteration — ZERO sync_to_async.

        Returns:
            list[dict] with id, title, slug, sub_title, description, created_at.
        """
        try:
            qs = (
                Collections.objects.values(
                    "id", "title", "slug", "sub_title", "description", "created_at"
                ).order_by("-created_at")
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_collections_list: %s", exc)
            return []

    @staticmethod
    async def aget_brands_list() -> list[dict]:
        """
        Async: return all active brands as list[dict].

        Uses .values() + async iteration — ZERO sync_to_async.

        Returns:
            list[dict] with id, title, slug, description, active, created_at.
        """
        try:
            qs = (
                Brand.objects.filter(active=True)
                .values("id", "title", "slug", "description", "active", "created_at")
                .order_by("title")
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_brands_list: %s", exc)
            return []

    @staticmethod
    async def aget_blog_posts_list(
        *,
        include_drafts: bool = False,
        limit: int = 20,
    ) -> list[dict]:
        """
        Async: return published blog posts as list[dict].

        Uses .values() + async iteration — ZERO sync_to_async.

        Args:
            include_drafts: If True, include non-published posts.
            limit: Max rows to return (default 20).

        Returns:
            list[dict] with id, title, slug, excerpt, status, is_featured,
            published_at, view_count, created_at, author__email, category__name.
        """
        try:
            qs = BlogPost.objects.values(
                "id",
                "title",
                "slug",
                "excerpt",
                "status",
                "is_featured",
                "published_at",
                "view_count",
                "created_at",
                "author__email",
                "category__name",
            )
            if not include_drafts:
                qs = qs.filter(
                    status=BlogPostStatus.PUBLISHED,
                    published_at__lte=timezone.now(),
                    is_deleted=False,
                )
            qs = qs.order_by("-is_featured", "-published_at", "-created_at")[:limit]
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_blog_posts_list: %s", exc)
            return []

    @staticmethod
    async def aget_category_product_count(category_slug: str) -> dict[str, Any]:
        """
        Async: return category metadata + live product count.

        Traversal: Category → Product M2M (product_categories reverse).
        Uses acount() — Django 6.0 native async ORM.
        ZERO sync_to_async.

        Args:
            category_slug: Slug of the category to look up.

        Returns:
            dict with id, name, slug, active, product_count.
            Empty dict if category not found.
        """
        try:
            from apps.product.models import Product
            cat = await Category.objects.aget(slug=category_slug, active=True)
            count = await Product.objects.filter(category=cat).acount()
            return {
                "id": str(cat.pk),
                "name": cat.name,
                "slug": cat.slug,
                "active": cat.active,
                "product_count": count,
            }
        except Category.DoesNotExist:
            return {}
        except Exception as exc:
            logger.error("aget_category_product_count slug=%s: %s", category_slug, exc)
            return {}

    @staticmethod
    async def aget_collection_vendor_count(collection_slug: str) -> dict[str, Any]:
        """
        Async: return collection metadata + live vendor count.

        Traversal: Collections → VendorProfile M2M (vendor_collections reverse).
        Uses acount() — Django 6.0 native async ORM.
        ZERO sync_to_async.

        Args:
            collection_slug: Slug of the collection to look up.

        Returns:
            dict with id, title, slug, sub_title, vendor_count.
            Empty dict if collection not found.
        """
        try:
            from apps.vendor.models import VendorProfile
            col = await Collections.objects.aget(slug=collection_slug)
            count = await VendorProfile.objects.filter(collections=col).acount()
            return {
                "id": col.pk,
                "title": col.title,
                "slug": col.slug,
                "sub_title": col.sub_title,
                "vendor_count": count,
            }
        except Collections.DoesNotExist:
            return {}
        except Exception as exc:
            logger.error("aget_collection_vendor_count slug=%s: %s", collection_slug, exc)
            return {}

    # ══════════════════════════════════════════════════════════════════
    #  HOMEPAGE BUNDLE SELECTORS  (Phase 11)
    #  All return list[dict] — minimal payload, maximum parallelism.
    #  These are called exclusively from the /catalog/homepage/ endpoint
    #  via asyncio.gather() — 5 queries in parallel, <30ms total.
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    async def aget_homepage_categories(limit: int = 10) -> list[dict]:
        """
        Async: first N active categories for homepage category grid.

        Returns:
            list[dict] with id, name, title, slug, image_url, active.
            Limited to ``limit`` rows, ordered by name (stable).

        Performance:
            .values() avoids model instantiation — no Cloudinary/storage
            descriptor evaluation at this level (image_url resolved in
            catalog_views serializer).
        """
        try:
            qs = (
                Category.objects.filter(active=True)
                .values("id", "name", "slug", "image", "active", "created_at")
                .order_by("name")[:limit]
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_homepage_categories: %s", exc)
            return []

    @staticmethod
    async def aget_homepage_collections(limit: int = 10) -> list[dict]:
        """
        Async: first N collections for homepage collection carousel.

        Returns:
            list[dict] with id, title, slug, sub_title, description, image, created_at.
            Limited to ``limit`` rows, ordered by newest-first.
        """
        try:
            qs = (
                Collections.objects.values(
                    "id",
                    "title",
                    "slug",
                    "sub_title",
                    "description",
                    "image",
                    "background_image",
                    "created_at",
                ).order_by("-created_at")[:limit]
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_homepage_collections: %s", exc)
            return []
