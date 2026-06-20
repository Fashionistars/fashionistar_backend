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
            Category.objects.filter(is_deleted=False)
            .only("id", "name", "slug", "image", "is_deleted", "created_at", "updated_at")
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

    # ══════════════════════════════════════════════════════════════════
    #  BANNER & TAG & SEARCH SELECTORS  (Phase B2)
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    async def aget_homepage_banners(slot: str = "hero", limit: int = 10) -> list[dict]:
        """
        Async: return active, scheduled CatalogBanners for a given slot.

        Scheduling: start_date=None → always live; end_date=None → never expires.

        Args:
            slot:  "hero" | "mid" | "footer_cta"
            limit: Max banners to return (default 10).

        Returns:
            list[dict] with id, slot, title, subtitle, cta_text, cta_url,
            image, mobile_image, sort_order.
        """
        try:
            import asyncio as _asyncio

            from django.db.models import Q

            from apps.catalog.models import CatalogBanner

            now = timezone.now()
            qs = (
                CatalogBanner.objects.filter(slot=slot, is_active=True)
                .filter(Q(start_date__isnull=True) | Q(start_date__lte=now))
                .filter(Q(end_date__isnull=True) | Q(end_date__gte=now))
                .values(
                    "id", "slot", "title", "subtitle",
                    "cta_text", "cta_url",
                    "image", "mobile_image", "sort_order",
                )
                .order_by("sort_order")[:limit]
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_homepage_banners slot=%s: %s", slot, exc)
            return []

    @staticmethod
    async def aget_trending_tags(limit: int = 20) -> list[dict]:
        """
        Async: return trending Tag records for the tags rail.

        Returns:
            list[dict] with id, name, slug, color_hex, is_trending.
        """
        try:
            from apps.catalog.models import Tag

            qs = (
                Tag.objects.filter(is_trending=True)
                .values("id", "name", "slug", "color_hex", "is_trending")
                .order_by("name")[:limit]
            )
            return [row async for row in qs]
        except Exception as exc:
            logger.error("aget_trending_tags: %s", exc)
            return []

    @staticmethod
    async def aget_catalog_search(q: str, limit: int = 24) -> dict:
        """
        Async: icontains search across Category + Brand + Collections.

        Args:
            q:     Raw search query string.
            limit: Max results per entity type.

        Returns:
            dict with keys categories, brands, collections (each list[dict]).
        """
        import asyncio as _asyncio

        async def _collect(qs):
            return [row async for row in qs]

        try:
            if not q or not q.strip():
                return {"categories": [], "brands": [], "collections": []}

            q = q.strip()

            categories_qs = (
                Category.objects.filter(active=True, name__icontains=q)
                .values("id", "name", "slug", "image")
                .order_by("name")[:limit]
            )
            brands_qs = (
                Brand.objects.filter(active=True, title__icontains=q)
                .values("id", "title", "slug", "image")
                .order_by("title")[:limit]
            )
            collections_qs = (
                Collections.objects.filter(title__icontains=q)
                .values("id", "title", "slug", "image")
                .order_by("-created_at")[:limit]
            )

            categories, brands, collections = await _asyncio.gather(
                _collect(categories_qs),
                _collect(brands_qs),
                _collect(collections_qs),
            )
            return {"categories": categories, "brands": brands, "collections": collections}
        except Exception as exc:
            logger.error("aget_catalog_search q=%r: %s", q, exc)
            return {"categories": [], "brands": [], "collections": []}

    @staticmethod
    async def aget_category_with_children(slug: str) -> dict | None:
        """
        Async: category detail dict including immediate children.

        Args:
            slug: Category slug.
        Returns:
            dict or None if not found.
        """
        try:
            cat = await Category.objects.aget(slug=slug, active=True)
            children_qs = (
                Category.objects.filter(parent=cat, active=True)
                .values("id", "name", "slug", "image", "sort_order", "icon_class", "color_hex")
                .order_by("sort_order", "name")
            )
            children = [row async for row in children_qs]
            return {
                "id": str(cat.pk),
                "name": cat.name,
                "slug": cat.slug or "",
                "meta_title": cat.meta_title,
                "meta_description": cat.meta_description,
                "image": str(cat.image) if cat.image else None,
                "banner_image": str(cat.banner_image) if cat.banner_image else None,
                "sort_order": cat.sort_order,
                "icon_class": cat.icon_class,
                "color_hex": cat.color_hex,
                "cached_product_count": cat.cached_product_count,
                "active": cat.active,
                "children": children,
            }
        except Category.DoesNotExist:
            return None
        except Exception as exc:
            logger.error("aget_category_with_children slug=%s: %s", slug, exc)
            return None

    @staticmethod
    async def aget_brand_detail(slug: str) -> dict | None:
        """
        Async: brand detail dict.

        Args:
            slug: Brand slug.
        Returns:
            dict or None if not found.
        """
        try:
            brand = await Brand.objects.aget(slug=slug, active=True)
            return {
                "id": str(brand.pk),
                "title": brand.title,
                "slug": brand.slug or "",
                "description": brand.description or "",
                "image": str(brand.image) if brand.image else None,
                "logo_banner": str(brand.logo_banner) if brand.logo_banner else None,
                "country": brand.country,
                "website_url": brand.website_url,
                "established_year": brand.established_year,
                "verified": brand.verified,
                "premium": brand.premium,
                "meta_title": brand.meta_title,
                "meta_description": brand.meta_description,
                "cached_product_count": brand.cached_product_count,
            }
        except Brand.DoesNotExist:
            return None
        except Exception as exc:
            logger.error("aget_brand_detail slug=%s: %s", slug, exc)
            return None

    @staticmethod
    async def aget_collection_detail(slug: str) -> dict | None:
        """
        Async: collection detail dict.

        Args:
            slug: Collection slug.
        Returns:
            dict or None if not found.
        """
        try:
            col = await Collections.objects.aget(slug=slug)
            return {
                "id": str(col.pk),
                "title": col.title or "",
                "slug": col.slug or "",
                "sub_title": col.sub_title or "",
                "description": col.description or "",
                "image": str(col.image) if col.image else None,
                "background_image": str(col.background_image) if col.background_image else None,
                "is_featured": col.is_featured,
                "sort_order": col.sort_order,
                "start_date": col.start_date.isoformat() if col.start_date else None,
                "end_date": col.end_date.isoformat() if col.end_date else None,
                "banner_cta_text": col.banner_cta_text,
                "banner_cta_url": col.banner_cta_url,
                "meta_title": col.meta_title,
                "meta_description": col.meta_description,
                "cached_product_count": col.cached_product_count,
                "is_active_now": col.is_active_now,
            }
        except Collections.DoesNotExist:
            return None
        except Exception as exc:
            logger.error("aget_collection_detail slug=%s: %s", slug, exc)
            return None
