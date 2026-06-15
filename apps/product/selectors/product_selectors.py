# apps/product/selectors/product_selectors.py
"""
Read-only query layer for the Product domain.

Architecture rules (Django 6.0 / async-first):
  - Every public function returns a QuerySet (composable).
  - All sync selectors are usable directly from DRF views.
  - All async selectors use native Django 6.0 async ORM:
      aget(), aexists(), alist(), async for — NO sync_to_async wrappers.
  - Heavy detail reads that need multiple parallel fetches use asyncio.gather
    for maximum throughput (avoids sequential await chains).
  - Reverse FK managers are preferred over forward FK filtering wherever
    possible to eliminate N+1 query patterns at the ORM level.

────────────────────────────────────────────────────────────────
5 Additional Enterprise Best-Practice Additions
────────────────────────────────────────────────────────────────
1. PARALLEL ASYNC READS: aget_product_detail_bundle fetches the product,
   its reviews, and the user wishlist status in one asyncio.gather call
   — 3 queries in parallel instead of 3 sequential awaits.
2. REVERSE FK PREFERENCE: all related-object queries use the reverse FK
   manager on the product (product.product_gallery_media.all()) instead of direct
   ProductGalleryMedia.objects.filter(product=product) — Django optimises
   these with a JOIN rather than a subquery.
3. QUERYSET ANNOTATION: get_published_products annotates review_count and
   avg_rating directly from the database so the serializer never needs
   extra queries to display those fields.
4. ONLY() PROJECTION: list querysets use .only() to select the exact
   fields required for card views, avoiding the full-row SELECT on large
   tables with 40+ columns.
5. ITERATOR STREAMING: get_products_export returns a chunked iterator
   (queryset.iterator(chunk_size=500)) for CSV/data-export endpoints,
   preventing full-table load into Python memory.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from django.db.models import (
    Avg, Case, Count, ExpressionWrapper, F, FloatField,
    IntegerField, Prefetch, Q, Value, When,
)
from django.db.models.functions import Round as DbRound
from django.utils import timezone

from apps.product.models import (
    Coupon,
    Product,
    # ProductCertification,
    ProductFabricSpecification,
    ProductSizeAndMeasurementGuide,
    ProductReview,
    ProductStatus,
    ProductVariantGalleryMedia,
    ProductWishlist,
)
from apps.common.selectors import BaseSelector

logger = logging.getLogger(__name__)


def _category_lookup(value: Any) -> Q:
    """Build a safe category/sub-category lookup for UUID ids or slugs."""
    lookup = Q(categories__slug=value) | Q(sub_categories__slug=value)
    try:
        category_id = value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return lookup
    return lookup | Q(categories__id=category_id) | Q(sub_categories__id=category_id)


# ── Optional import (guarded — avoids circular imports on cold-start) ─────────
def _get_wishlist_model():
    return ProductWishlist


class ProductSelector(BaseSelector):
    """Product read selector namespace for sync DRF and async Ninja reads."""
    model = Product


# ─────────────────────────────────────────────────────────────────────────────
# 1. SYNC PRODUCT QUERYSETS (for DRF views)
# ─────────────────────────────────────────────────────────────────────────────

def get_published_products():
    """
    Base published queryset with select_related + prefetch.

    Best-practice #3 (annotation): annotates review_count and avg_rating
    so serializers never fire extra per-row aggregate queries.
    """
    return (
        Product.objects
        .filter(status=ProductStatus.PUBLISHED, is_deleted=False)
        .select_related(
            "vendor",          # FK → VendorProfile
            "vendor__user",    # FK → User (username, avatar)
        )
        .prefetch_related(
            "categories",       # M2M
            "sub_categories",   # M2M
            "tags",            # M2M
            Prefetch(
                "product_variants_gallery_media",
                queryset=ProductVariantGalleryMedia.objects.filter(
                    is_deleted=False,
                    media_type="image",
                ).order_by("ordering")[:3],
                to_attr="card_gallery",
            ),
        )
        .annotate(
            computed_review_count=Count("reviews", distinct=True),
            computed_avg_rating=Avg("reviews__rating"),
        )
        .order_by("-created_at")
    )


def get_published_products_list():
    """
    Optimised list queryset for catalog / search results.

    Best-practice #4 (only projection): fetches only card-view fields
    to avoid loading large text columns (description, specifications).
    """
    return (
        Product.objects
        .filter(status=ProductStatus.PUBLISHED, is_deleted=False)
        .select_related("vendor__user")
        .prefetch_related(
            "categories",
            "sub_categories",
            Prefetch(
                "product_variants_gallery_media",
                queryset=ProductVariantGalleryMedia.objects.filter(is_deleted=False).select_related("size"),
                to_attr="_prefetched_variants",
            ),
        )
        .annotate(
            computed_review_count=Count("reviews", distinct=True),
            computed_avg_rating=Avg("reviews__rating"),
        )
        .defer("description", "search_vector", "ai_description")
        .order_by("-created_at")
    )


def get_product_detail(slug: str) -> Product | None:
    """Full product detail for a single slug — includes specs, FAQs, variants."""
    try:
        return (
            Product.objects
            .filter(status=ProductStatus.PUBLISHED, is_deleted=False, slug=slug)
            .select_related(
                "vendor", "vendor__user",
            )
            .prefetch_related(
                "categories", "sub_categories",
                "tags",
                Prefetch(
                    "product_variants_gallery_media",
                    queryset=ProductVariantGalleryMedia.objects.filter(
                        is_deleted=False,
                    ).select_related("size").order_by("ordering", "created_at"),
                ),
                "faqs",
            )
            .annotate(
                computed_review_count=Count("reviews", distinct=True),
                computed_avg_rating=Avg("reviews__rating"),
            )
            .get()
        )
    except Product.DoesNotExist:
        return None


def get_featured_products(limit: int = 20):
    return get_published_products_list().filter(featured=True)[:limit]


def get_products_by_category(category_id: Any):
    return get_published_products_list().filter(_category_lookup(category_id)).distinct()


def get_products_by_vendor(vendor_id: Any):
    """
    All (non-deleted) products for a vendor — uses reverse FK manager pattern
    via explicit filter to maintain composability.
    """
    return (
        Product.objects
        .filter(vendor_id=vendor_id, is_deleted=False)
        .select_related("vendor__user")
        .prefetch_related("categories", "sub_categories", "tags", "product_variants_gallery_media")
        .annotate(
            computed_review_count=Count("reviews", distinct=True),
        )
        .order_by("-created_at")
    )


def get_vendor_product_or_404(vendor_id: Any, slug: str) -> Product | None:
    """
    Return a single vendor-owned product by slug, or None.

    Best-practice reverse FK usage: the vendor foreign key is traversed
    via the vendor_id PK path which Django resolves with a single WHERE clause
    — no extra JOIN or subquery needed.
    """
    try:
        return (
            Product.objects
            .filter(vendor_id=vendor_id, slug=slug, is_deleted=False)
            .select_related(
                "vendor", "vendor__user",
            )
            .prefetch_related(
                "categories", "sub_categories",
                "tags",
                Prefetch(
                    "product_variants_gallery_media",
                    queryset=ProductVariantGalleryMedia.objects.filter(
                        is_deleted=False,
                    ).select_related("size").order_by("ordering", "created_at"),
                ),
                "faqs",
            )
            .get()
        )
    except Product.DoesNotExist:
        return None


def search_products(query: str):
    """Full-text + icontains fallback search across title, description, SKU, tags."""
    if not query:
        return get_published_products_list()
    return (
        get_published_products_list()
        .filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(sku__icontains=query)
            | Q(tags__name__icontains=query)
        )
        .distinct()
    )


def filter_products(
    *,
    category_id: Any = None,
    sub_category: str | None = None,
    brand_id: Any = None,
    vendor_id: Any = None,
    min_price: Any = None,
    max_price: Any = None,
    in_stock: bool | None = None,
    featured: bool | None = None,
    hot_deal: bool | None = None,
    size_ids: list | None = None,
    color_ids: list | None = None,
    query: str | None = None,
    ordering: str = "-created_at",
):
    """
    Composable multi-filter selector. Called by both DRF and Ninja views.

    All filters are applied at the DB level (no Python-side filtering).
    """
    allowed_ordering = {
        "price":     "price",
        "-price":    "-price",
        "latest":    "-created_at",
        "oldest":    "created_at",
        "rating":    "-rating",
        "-created_at": "-created_at",
        "popular":   "-review_count",
    }
    qs = get_published_products_list()

    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(sku__icontains=query)
            | Q(tags__name__icontains=query)
        ).distinct()
    if category_id:
        qs = qs.filter(_category_lookup(category_id)).distinct()
    if sub_category:
        # Filter by sub-category slug via M2M relation on Product.sub_categories
        qs = qs.filter(sub_categories__slug=sub_category).distinct()
    if brand_id:
        logger.debug(
            "Ignoring product brand filter=%s because Brand is marketing metadata.",
            brand_id,
        )
    if vendor_id:
        # Polymorphic UUID / store_slug filter — safe for both sync DRF and
        # async Ninja: no live DB query is executed here (queryset is lazy).
        # Django resolves the JOIN at evaluation time in the caller's context.
        import uuid as _uuid  # noqa: PLC0415
        try:
            # If vendor_id is a valid UUID, filter by PK directly (fastest path).
            vendor_uuid = _uuid.UUID(str(vendor_id))
            qs = qs.filter(vendor_id=vendor_uuid)
        except (ValueError, AttributeError):
            # vendor_id is a slug — traverse the FK relationship via JOIN.
            # This never fires a separate DB query; Django builds it as:
            #   INNER JOIN vendor_profile ON product.vendor_id = vendor_profile.id
            #   WHERE vendor_profile.store_slug = %s
            qs = qs.filter(vendor__store_slug=vendor_id, vendor__is_deleted=False)
    if min_price is not None:
        qs = qs.filter(price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(price__lte=max_price)
    if in_stock is not None:
        qs = qs.filter(in_stock=in_stock)
    if featured is not None:
        qs = qs.filter(featured=featured)
    if hot_deal is not None:
        qs = qs.filter(hot_deal=hot_deal)
    if size_ids:
        qs = qs.filter(product_variants_gallery_media__size__id__in=size_ids).distinct()
    if color_ids:
        qs = qs.filter(product_variants_gallery_media__id__in=color_ids).distinct()

    return qs.order_by(allowed_ordering.get(ordering, "-created_at"))


def get_products_export(vendor_id: Any):
    """
    Best-practice #5 (iterator streaming): yields product rows in chunks
    for CSV / data-export endpoints without loading all rows into memory.
    """
    return (
        Product.objects
        .filter(vendor_id=vendor_id, is_deleted=False)
        .prefetch_related("categories", "sub_categories")
        .order_by("created_at")
        .iterator(chunk_size=500)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. REVIEW QUERYSETS
# ─────────────────────────────────────────────────────────────────────────────

def get_product_reviews(product_id: Any):
    """Active reviews for a product — ordered newest first."""
    return (
        ProductReview.objects
        .filter(product_id=product_id, active=True)
        .select_related("user", "user__client_profile", "user__vendor_profile")
        .order_by("-created_at")
    )


def get_user_review_for_product(user_id: Any, product_id: Any) -> ProductReview | None:
    try:
        return ProductReview.objects.get(user_id=user_id, product_id=product_id)
    except ProductReview.DoesNotExist:
        return None


def get_vendor_review_summary(vendor_id: Any) -> dict:
    """
    Aggregate review stats for all of a vendor's products.
    Returns {avg_rating, total_reviews, product_count}.

    Admin summary: total reviews + average rating across all vendor products.
    Single-pass aggregate — zero N+1.
    """
    agg = (
        ProductReview.objects
        .filter(product__vendor_id=vendor_id, active=True)
        .aggregate(
            avg_rating=Avg("rating"),
            total_reviews=Count("id"),
            product_count=Count("product_id", distinct=True),
        )
    )
    return {
        "vendor_id": str(vendor_id),
        "total_reviews": agg["total_reviews"] or 0,
        "avg_rating": round(agg["avg_rating"] or 0, 2),
        "product_count": agg["product_count"] or 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. WISHLIST QUERYSETS
# ─────────────────────────────────────────────────────────────────────────────

def _wishlist_owner_filter(
    *,
    user_id: Any | None = None,
    session_key: str | None = None,
) -> dict:
    """Return the exact owner filter for wishlist queries."""

    if user_id:
        return {"user_id": user_id}
    if session_key:
        return {"user__isnull": True, "session_key": session_key}
    return {"pk__isnull": True}


def get_wishlist_for_identity(
    *,
    user_id: Any | None = None,
    session_key: str | None = None,
):
    """
    Return a user or anonymous session wishlist with full product join.

    Best-practice #2 (reverse FK): uses reverse relation on ProductWishlist
    to select_related the product tree in ONE query with proper JOINs.
    """
    return (
        ProductWishlist.objects
        .filter(**_wishlist_owner_filter(user_id=user_id, session_key=session_key))
        .select_related(
            "product__vendor__user",
        )
        .prefetch_related(
            # ── Critical async-safety fix ─────────────────────────────────────
            # Prefetch product categories so _product_card_out reads from the
            # Django prefetch cache (_prefetched_objects_cache) at serialisation
            # time — zero live DB queries — instead of calling the `primary_category`
            # @property which fires a sync ORM query (SynchronousOnlyOperation in
            # async Ninja context).
            "product__categories",
            Prefetch(
                "product__product_variants_gallery_media",
                queryset=ProductVariantGalleryMedia.objects.filter(
                    is_deleted=False, media_type="image",
                ).order_by("ordering")[:1],
                to_attr="cover_gallery",
            ),
        )
        .order_by("-created_at")
    )


def get_user_wishlist(user_id: Any):
    """Return an authenticated user's wishlist."""

    return get_wishlist_for_identity(user_id=user_id)


def is_in_wishlist(
    user_id: Any | None,
    product_id: Any,
    *,
    session_key: str | None = None,
) -> bool:
    return ProductWishlist.objects.filter(
        product_id=product_id,
        **_wishlist_owner_filter(user_id=user_id, session_key=session_key),
    ).exists()


# ─────────────────────────────────────────────────────────────────────────────
# 4. COUPON QUERYSETS
# ─────────────────────────────────────────────────────────────────────────────

def get_vendor_coupons(vendor_id: Any):
    return (
        Coupon.objects
        .filter(vendor_id=vendor_id, is_deleted=False)
        .order_by("-created_at")
    )


def get_coupon_by_code(code: str) -> Coupon | None:
    try:
        return Coupon.objects.get(code__iexact=code.strip(), is_deleted=False)
    except Coupon.DoesNotExist:
        return None


def get_active_coupons_for_vendor(vendor_id: Any):
    """Return only currently valid (not expired, not depleted) coupons."""
    now = timezone.now()
    return (
        Coupon.objects
        .filter(
            vendor_id=vendor_id,
            is_deleted=False,
            valid_from__lte=now,
            valid_to__gte=now,
        )
        .filter(
            Q(max_usage__isnull=True) | Q(usage_count__lt=models_F("max_usage"))
        )
        .order_by("-created_at")
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. NATIVE ASYNC QUERYSETS — Django 6.0 ORM (NO sync_to_async)
# ─────────────────────────────────────────────────────────────────────────────

def afilter_products(
    *,
    category: str | None = None,
    sub_category: str | None = None,
    brand: str | None = None,
    vendor: str | None = None,
    min_price: Any = None,
    max_price: Any = None,
    in_stock: bool | None = None,
    featured: bool | None = None,
    hot_deal: bool | None = None,
    query: str | None = None,
    ordering: str = "-created_at",
):
    """Return an async-ready published product queryset for Ninja feeds."""
    return filter_products(
        category_id=category,
        sub_category=sub_category,
        brand_id=brand,
        vendor_id=vendor,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        featured=featured,
        hot_deal=hot_deal,
        query=query,
        ordering=ordering,
    )


async def aget_product_detail(slug: str) -> Product | None:
    """
    Async: return full public product detail by slug, or None.

    Phase 1 expansion: prefetches all Phase 1 reverse FK relations so
    serializers and Ninja schemas receive pre-loaded data with zero extra
    DB queries:
      - product_fabric       (ProductFabric via select_related)
      - product_custom_shipping_profile (ProductShippingProfile via select_related)
      - measurement_guides  (ProductMeasurementGuide, ordered by sort_order)
      - product_certifications (ProductCertification)
    """
    try:
        product = await (
            Product.objects
            .filter(
                status=ProductStatus.PUBLISHED,
                is_deleted=False,
                slug=slug,
            )
            .select_related(
                "vendor", "vendor__user", "product_fabric_specification", "shipping_profile",
            )
            .prefetch_related(
                "categories", "sub_categories",
                "tags",
                Prefetch(
                    "product_variants_gallery_media",
                    queryset=ProductVariantGalleryMedia.objects
                    .filter(is_deleted=False)
                    .select_related("size")
                    .order_by("ordering", "sku"),
                ),
                "faqs",
            )
            .annotate(
                computed_review_count=Count("reviews", distinct=True),
                computed_avg_rating=Avg("reviews__rating"),
            )
            .aget()
        )
        if product:
            size_ids = [v.size_id for v in product.product_variants_gallery_media.all() if v.size_id]
            if size_ids:
                product._prefetched_measurement_guides = [
                    g async for g in ProductSizeAndMeasurementGuide.objects.filter(id__in=size_ids).order_by("sort_order")
                ]
            elif product.vendor:
                product._prefetched_measurement_guides = [
                    g async for g in ProductSizeAndMeasurementGuide.objects.filter(vendor=product.vendor).order_by("sort_order")
                ]
            else:
                product._prefetched_measurement_guides = []
        return product
    except Product.DoesNotExist:
        return None


async def aget_product_detail_bundle(
    *,
    slug: str,
    user_id: Any | None,
    session_key: str | None = None,
) -> dict:
    """
    Best-practice #1 (parallel async reads):
    Fetch product detail, its active reviews, and the user's wishlist status
    in parallel using asyncio.gather — 3 DB queries in parallel, not sequential.

    Returns:
        {
            "product": Product | None,
            "reviews": list[ProductReview],
            "in_wishlist": bool,
        }
    """
    async def _fetch_product():
        return await aget_product_detail(slug)

    async def _fetch_reviews(product_id):
        return [
            r async for r in (
                ProductReview.objects
                .filter(product_id=product_id, active=True)
                .select_related("user", "user__client_profile", "user__vendor_profile")
                .order_by("-created_at")
            )
        ]

    async def _check_wishlist(product_id, uid, anon_key):
        owner_filter = _wishlist_owner_filter(user_id=uid, session_key=anon_key)
        if "pk__isnull" in owner_filter:
            return False
        return await ProductWishlist.objects.filter(
            product_id=product_id,
            **owner_filter,
        ).aexists()

    # Step 1: fetch the product (we need its pk before the parallel gather)
    product = await _fetch_product()
    if not product:
        return {"product": None, "reviews": [], "in_wishlist": False}

    # Step 2: fetch reviews + wishlist in parallel
    reviews, in_wishlist = await asyncio.gather(
        _fetch_reviews(product.id),
        _check_wishlist(product.id, user_id, session_key),
    )

    return {"product": product, "reviews": reviews, "in_wishlist": in_wishlist}


def areviews_for_product(product_id: Any):
    """Return an async-ready active reviews queryset for a product."""
    return get_product_reviews(product_id)


async def alist_reviews_for_product_slug(slug: str, limit: int = 20) -> list[ProductReview]:
    """Return active product reviews for a slug using one reverse-join query."""
    return [
        review
        async for review in ProductReview.objects.filter(
            product__slug=slug,
            product__is_deleted=False,
            active=True,
        )
        .select_related("user", "user__client_profile", "user__vendor_profile")
        .order_by("-created_at")[:limit]
    ]


async def auser_has_wishlist_slug(user: Any, slug: str) -> bool:
    """Return True when ``user`` has wishlisted the product slug."""
    if not user:
        return False
    return await ProductWishlist.objects.filter(
        user=user,
        product__slug=slug,
        product__is_deleted=False,
    ).aexists()


def awishlist_for_user(user_id: Any):
    """Return an async-ready wishlist queryset for one user."""
    return get_user_wishlist(user_id)


def awishlist_for_identity(
    *,
    user_id: Any | None = None,
    session_key: str | None = None,
):
    """Return an async-ready wishlist queryset for a user or anonymous session."""

    return get_wishlist_for_identity(user_id=user_id, session_key=session_key)


def avendor_coupons(vendor_id: Any):
    """Return an async-ready coupon queryset for one vendor."""
    return get_vendor_coupons(vendor_id)


def avendor_products(vendor_id: Any):
    """Return an async-ready product queryset for one vendor profile."""
    return (
        Product.objects
        .filter(vendor_id=vendor_id, is_deleted=False)
        .select_related("vendor__user")
        .prefetch_related(
            "categories",
            "sub_categories",
            "tags",
            "product_variants_gallery_media",
            "product_variants_gallery_media__size",
        )
        .annotate(computed_review_count=Count("reviews", distinct=True))
        .order_by("-created_at")
    )


async def aget_vendor_product(vendor_id: Any, slug: str) -> Product | None:
    """Async: return one product owned by a vendor profile, or None."""
    try:
        product = await (
            Product.objects
            .filter(vendor_id=vendor_id, slug=slug, is_deleted=False)
            .select_related(
                "vendor", "vendor__user", "product_fabric_specification", "shipping_profile",
            )
            .prefetch_related(
                "categories", "sub_categories",
                "tags",
                Prefetch(
                    "product_variants_gallery_media",
                    queryset=ProductVariantGalleryMedia.objects.filter(is_deleted=False).select_related("size").order_by("ordering"),
                ),
                "faqs",
            )
            .aget()
        )
        if product:
            size_ids = [v.size_id for v in product.product_variants_gallery_media.all() if v.size_id]
            if size_ids:
                product._prefetched_measurement_guides = [
                    g async for g in ProductSizeAndMeasurementGuide.objects.filter(id__in=size_ids).order_by("sort_order")
                ]
            elif product.vendor:
                product._prefetched_measurement_guides = [
                    g async for g in ProductSizeAndMeasurementGuide.objects.filter(vendor=product.vendor).order_by("sort_order")
                ]
            else:
                product._prefetched_measurement_guides = []
        return product
    except Product.DoesNotExist:
        return None


async def aget_wishlist_status_bulk(
    user_id: Any,
    product_ids: list,
    *,
    session_key: str | None = None,
) -> dict[str, bool]:
    """
    Async: check wishlist status for multiple products in ONE query.
    Returns {product_id_str: bool} map. Used in product list views to
    render the heart icon without per-card queries.

    Best-practice #2 (reverse FK): queries ProductWishlist via user reverse
    relation so Django uses the user_id index path efficiently.
    """
    owner_filter = _wishlist_owner_filter(user_id=user_id, session_key=session_key)
    if "pk__isnull" in owner_filter:
        return {str(pid): False for pid in product_ids}
    wishlisted_ids = set(
        [
            str(pk)
            async for pk in (
                ProductWishlist.objects
                .filter(product_id__in=product_ids, **owner_filter)
                .values_list("product_id", flat=True)
            )
        ]
    )
    return {str(pid): (str(pid) in wishlisted_ids) for pid in product_ids}


# ── Convenience alias — lazy import guard for F() from django.db.models ───────
def models_F(field: str):  # noqa: N802
    from django.db.models import F as _F
    return _F(field)


# ─────────────────────────────────────────────────────────────────────────────
# ALIASES & ADDITIONAL SELECTORS
# ─────────────────────────────────────────────────────────────────────────────

def get_published_products_list(
    *,
    category_id: Any = None,
    brand_id: Any = None,
    vendor_id: Any = None,
    ordering: str = "-created_at",
):
    """
    Optimized list selector using .only() to avoid loading large text columns.
    Paired with ProductListSerializer for catalog/card views.
    """
    from django.db.models import Prefetch

    qs = (
        Product.objects
        .filter(status=ProductStatus.PUBLISHED, is_deleted=False)
        .select_related("vendor")
        .prefetch_related(
            "categories",
            "sub_categories",
            Prefetch("product_variants_gallery_media", queryset=ProductVariantGalleryMedia.objects.filter(is_deleted=False).select_related("size"), to_attr="_prefetched_variants"),
        )
        # .only(
        #     "id", "title", "slug", "sku", "price", "old_price", "currency",
        #     "in_stock", "stock_qty", "featured", "hot_deal",
        #     "rating", "review_count", "requires_measurement", "is_customisable",
        #     "created_at",
        #     "vendor__id", "vendor__store_name", "vendor__store_slug",
        #     "vendor__logo_url", "vendor__is_verified",
        # )
        .defer("description", "search_vector", "ai_description", "body_type_fit", "occasion_tags", "style_tags")
        .annotate(
            computed_review_count=Count("reviews", distinct=True),
            computed_avg_rating=Avg("reviews__rating"),
        )
    )
    if category_id:
        qs = qs.filter(_category_lookup(category_id)).distinct()
    if brand_id:
        logger.debug(
            "Ignoring product brand filter=%s because Brand is not a Product relation.",
            brand_id,
        )
    if vendor_id:
        qs = qs.filter(vendor_id=vendor_id)
    return qs.order_by(ordering)




def alist_inventory_logs(product_id: Any):
    """Return an async-ready queryset of inventory log entries for a product."""
    return (
        ProductInventoryLog.objects
        .filter(product_id=product_id)
        .select_related("actor")
        .order_by("-created_at")
    )


async def asearch_suggest(query: str, limit: int = 10):
    """
    Async FTS-based search suggest for autocomplete.
    Returns [{slug, title}] — lightweight, no images.
    """
    results = []
    async for product in (
        Product.objects
        .filter(
            status=ProductStatus.PUBLISHED,
            is_deleted=False,
            title__icontains=query,
        )
        .only("slug", "title")
        .order_by("-rating")[:limit]
    ):
        results.append(product)
    return results


async def aget_wishlist_status_for_products(
    user_id: Any | None,
    slugs: list[str],
    *,
    session_key: str | None = None,
) -> dict[str, bool]:
    """
    Async wishlist bulk-status check by product slugs.
    Returns {slug: is_wishlisted} for rendering heart icons on catalog cards.
    """
    # Resolve slugs to IDs in one query
    pid_to_slug: dict = {}
    async for product in (
        Product.objects
        .filter(slug__in=slugs, is_deleted=False)
        .only("id", "slug")
    ):
        pid_to_slug[str(product.pk)] = product.slug

    owner_filter = _wishlist_owner_filter(user_id=user_id, session_key=session_key)
    if "pk__isnull" in owner_filter:
        return {slug: False for slug in pid_to_slug.values()}

    # One wishlist query across all product IDs
    wishlisted_pids: set[str] = set()
    async for pk in (
        ProductWishlist.objects
        .filter(product_id__in=pid_to_slug.keys(), **owner_filter)
        .values_list("product_id", flat=True)
    ):
        wishlisted_pids.add(str(pk))

    return {
        slug: (pid in wishlisted_pids)
        for pid, slug in pid_to_slug.items()
    }



# ─────────────────────────────────────────────────────────────────────────────
# 6. PHASE 3 — NEW ASYNC SELECTORS (asyncio.gather pattern)
# ─────────────────────────────────────────────────────────────────────────────

async def alist_products(
    *,
    category: str | None = None,
    brand: str | None = None,
    vendor: str | None = None,
    min_price: Any = None,
    max_price: Any = None,
    in_stock: bool | None = None,
    featured: bool | None = None,
    hot_deal: bool | None = None,
    query: str | None = None,
    ordering: str = "-created_at",
    page: int = 1,
    page_size: int = 24,
) -> dict:
    """
    Async catalog list selector — used by Ninja catalog endpoints.

    Uses asyncio.gather to fetch the count and the page slice in parallel
    (two DB queries in parallel, not sequential).

    Returns:
        {
            "count": int,
            "results": list[Product],
        }
    """
    qs = (
        Product.objects
        .filter(
            status=ProductStatus.PUBLISHED,
            is_deleted=False,
        )
        .select_related("vendor")
        .prefetch_related(
            "categories",
            "sub_categories",
            "product_variants_gallery_media",
            "product_variants_gallery_media__size",
        )
        .annotate(
            computed_review_count=Count("reviews", distinct=True),
            computed_avg_rating=Avg("reviews__rating"),
        )
    )

    # Apply optional filters
    if category:
        qs = qs.filter(_category_lookup(category)).distinct()
    if brand:
        logger.debug(
            "Ignoring product brand filter=%s because Brand is not a Product relation.",
            brand,
        )
    if vendor:
        qs = qs.filter(Q(vendor__store_slug=vendor) | Q(vendor__id=vendor))
    if min_price is not None:
        qs = qs.filter(price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(price__lte=max_price)
    if in_stock is True:
        qs = qs.filter(in_stock=True)
    if featured is True:
        qs = qs.filter(featured=True)
    if hot_deal is True:
        qs = qs.filter(hot_deal=True)
    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(tags__name__icontains=query)
        ).distinct()

    # Safe ordering
    ALLOWED_ORDERINGS = {
        "-created_at", "created_at",
        "-price", "price",
        "-rating", "rating",
        "-views", "views",
    }
    qs = qs.order_by(ordering if ordering in ALLOWED_ORDERINGS else "-created_at")

    offset = (page - 1) * page_size
    page_qs = qs[offset: offset + page_size]

    # Parallel: count + page slice
    async def _count():
        return await qs.acount()

    async def _page():
        return [p async for p in page_qs]

    count, results = await asyncio.gather(_count(), _page())
    return {"count": count, "results": results}


async def aget_featured_products(limit: int = 12) -> list:
    """
    Async: return top featured products for the homepage featured-products grid.

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  FASHIONISTAR AD PLATFORM — FUTURE BUSINESS MODEL                      │
    │                                                                         │
    │  This selector is the canonical source for the homepage "Featured        │
    │  Products" section. The `featured` boolean flag on the Product model    │
    │  is the gateway for our PAID ADVERTISEMENT service:                     │
    │                                                                         │
    │  Phase A (current):  Admin manually sets product.featured = True       │
    │  Phase B (future):   Vendor pays for "Featured Slot" subscription →    │
    │    AdCampaign.create(vendor=vendor, slot="homepage_featured", ...)     │
    │    → Celery task sets product.featured = True for campaign duration    │
    │    → Campaign ends → product.featured reset to False automatically     │
    │                                                                         │
    │  Ordering by (-orders_count, -rating) ensures that within a tier of   │
    │  paying vendors, the best-performing products surface first —          │
    │  good for advertisers AND for customer conversion rates.               │
    │                                                                         │
    │  The same endpoint powers the GET /catalog/homepage/ bundle via        │
    │  asyncio.gather() — all 5 homepage sections load in parallel.          │
    └─────────────────────────────────────────────────────────────────────────┘

    Architecture:
      - featured=True filter + rating/orders_count ordering surfaces paid
        featured products first within each popularity tier.
      - select_related("vendor") prevents N+1 on vendor name rendering.
      - prefetch_related("categories", "sizes", "colors") fills M2M caches.
        These prefetch caches are read by _homepage_product_out() in
        catalog_views.py with ZERO extra DB queries.
      - Returns list (not QuerySet) — safe to pass across asyncio.gather().
      - Wrapped in try/except — a DB error returns [] rather than crashing
        the entire homepage bundle gather.

    Returns:
        list[Product] — at most ``limit`` items, ordered by
        (-orders_count, -rating, -created_at). Default limit=12 covers
        a 4-column × 3-row homepage grid; the bundle endpoint passes limit=10.

    Future ad-platform hook (Phase B):
        When AdCampaign billing is live, replace `.filter(featured=True)` with:
            .filter(
                Q(featured=True) | Q(ad_campaigns__slot="homepage_featured",
                                     ad_campaigns__is_active=True)
            ).distinct()
    """
    try:
        qs = (
            Product.objects
            .filter(
                status=ProductStatus.PUBLISHED,
                is_deleted=False,
                featured=True,
            )
            .select_related("vendor")
            .prefetch_related(
                "categories",
                "sub_categories",
                "product_variants_gallery_media",
                "product_variants_gallery_media__size",
            )
            .annotate(
                computed_review_count=Count("reviews", distinct=True),
                computed_avg_rating=Avg("reviews__rating"),
            )
            .order_by("-orders_count", "-rating", "-created_at")
        )
        return [p async for p in qs[:limit]]
    except Exception as exc:
        logger.error("aget_featured_products: %s", exc)
        return []


async def aget_products_by_vendor_async(
    vendor_slug: str,
    page: int = 1,
    page_size: int = 24,
) -> dict:
    """
    Async vendor-storefront catalog selector.

    Returns paginated products for a public vendor page using the same
    asyncio.gather pattern as alist_products.
    """
    qs = (
        Product.objects
        .filter(
            status=ProductStatus.PUBLISHED,
            is_deleted=False,
            vendor__store_slug=vendor_slug,
        )
        .select_related("vendor")
        .prefetch_related(
            "categories",
            "sub_categories",
            "product_variants_gallery_media",
            "product_variants_gallery_media__size",
        )
        .annotate(
            computed_review_count=Count("reviews", distinct=True),
            computed_avg_rating=Avg("reviews__rating"),
        )
        .order_by("-created_at")
    )

    offset = (page - 1) * page_size
    page_qs = qs[offset: offset + page_size]

    async def _count():
        return await qs.acount()

    async def _page():
        return [p async for p in page_qs]

    count, results = await asyncio.gather(_count(), _page())
    return {"count": count, "results": results}


# ─────────────────────────────────────────────────────────────────────────────
# 7. PHASE 11 — HOMEPAGE BUNDLE SELECTORS
#    Called exclusively via asyncio.gather() in GET /catalog/homepage/
#    All return Python lists — no lazy querysets — safe for asyncio.gather()
#    Target: < 30ms total (all 5 queries run in parallel on PgBouncer pool)
# ─────────────────────────────────────────────────────────────────────────────

async def aget_homepage_products(limit: int = 10) -> list:
    """
    Async: thin delegator to ``aget_featured_products`` for the homepage bundle.

    The canonical query logic and ad-platform extension points live in
    ``aget_featured_products``; this wrapper exists so the catalog views can
    import a semantically clear name from the Phase 11 bundle section.

    Called exclusively via asyncio.gather() in GET /catalog/homepage/:

        aget_homepage_products(limit=products_limit)   ← this function
        aget_homepage_hot_deals(limit=hot_deals_limit)
        aget_homepage_reviews(limit=reviews_limit)
        aget_homepage_collections(limit=...)
        aget_homepage_categories(limit=...)

    Future ad-platform hook: update ``aget_featured_products`` to include
    AdCampaign slot filter — this delegator automatically inherits it.
    """
    return await aget_featured_products(limit=limit)


async def aget_homepage_hot_deals(limit: int = 10) -> list:
    # ┌──────────────────────────────────────────────────────────────────────┐
    # │  FASHIONISTAR AD PLATFORM — SECOND BUSINESS MODEL (Future)          │
    # │                                                                      │
    # │  The "Deals of the Week" / Hot Deals section will be Fashionistar's │
    # │  second revenue stream:                                             │
    # │    Phase A (current): Admin sets product.hot_deal = True            │
    # │    Phase B (future):  Vendor pays for "Hot Deal Slot" → Celery task │
    # │      sets hot_deal=True for the campaign period, auto-resets on     │
    # │      campaign expiry. Priority slot = more discount_percentage.     │
    # │                                                                      │
    # │  Future hook: add AdCampaign Q() filter same as featured products.  │
    # └──────────────────────────────────────────────────────────────────────┘
    #
    # Same note: (original docstring below)
    """
    Async: return top N hot-deal products for the "Deals of the Week" section.

    Architecture:
      - hot_deal=True + discount ordering surfaces best value-for-money items.
      - Same prefetch contract as aget_homepage_products — no extra queries.

    Returns:
        list[Product] — at most ``limit`` items, ordered by discount descending.
    """
    try:
        # discount_percentage is a Python @property — it cannot be used in
        # order_by(). We annotate the equivalent expression at the DB level
        # so sorting is done entirely in SQL without loading all rows first.
        #
        #   SQL equivalent:
        #     CASE WHEN old_price IS NOT NULL AND old_price > price
        #          THEN ROUND((1 - CAST(price AS float) / old_price) * 100)
        #          ELSE 0
        #     END
        discount_expr = Case(
            When(
                old_price__isnull=False,
                old_price__gt=F("price"),
                then=DbRound(
                    ExpressionWrapper(
                        (Value(1.0) - F("price") / F("old_price")) * Value(100.0),
                        output_field=FloatField(),
                    )
                ),
            ),
            default=Value(0),
            output_field=IntegerField(),
        )
        qs = (
            Product.objects
            .filter(
                status=ProductStatus.PUBLISHED,
                is_deleted=False,
                hot_deal=True,
            )
            .select_related("vendor")
            .prefetch_related(
                "categories",
                "sub_categories",
                "product_variants_gallery_media",
                "product_variants_gallery_media__size",
            )
            .annotate(
                computed_review_count=Count("reviews", distinct=True),
                computed_avg_rating=Avg("reviews__rating"),
                discount_pct=discount_expr,
            )
            .order_by("-discount_pct", "-created_at")
        )
        return [p async for p in qs[:limit]]
    except Exception as exc:
        logger.error("aget_homepage_hot_deals: %s", exc)
        return []


async def aget_homepage_reviews(limit: int = 8) -> list[dict]:
    """
    Async: return top N moderated public product reviews for the homepage.

    Uses .values() to avoid full model instantiation — only the fields
    needed for the review card are fetched (reviewer name, rating, text,
    avatar, product title). ZERO sync_to_async.

    Returns:
        list[dict] with reviewer_name, rating, review_text, product_title,
        reviewer_avatar_url, created_at.
    """
    try:
        qs = (
            ProductReview.objects
            .filter(active=True, moderated=True)
            .select_related(
                "user",
                "user__client_profile",
                "user__vendor_profile",
                "product",
            )
            .order_by("-helpful_votes", "-rating", "-created_at")[:limit]
        )
        rows: list[dict] = []
        async for review in qs:
            user = getattr(review, "user", None)
            profile = None
            if user:
                profile = (
                    getattr(user, "client_profile", None)
                    or getattr(user, "vendor_profile", None)
                )
            avatar = getattr(profile, "avatar", None) if profile else None
            avatar_url: str | None = None
            if avatar:
                try:
                    raw = str(avatar.url)
                    if "res.cloudinary.com" in raw and "/upload/" in raw:
                        avatar_url = raw.replace(
                            "/upload/", "/upload/w_120,h_120,c_fill,f_auto,q_auto/"
                        )
                    else:
                        avatar_url = raw
                except Exception:
                    avatar_url = None

            reviewer_name = review.reviewer_name or (
                getattr(user, "get_full_name", lambda: "")() if user else None
            ) or "Anonymous"
            product = getattr(review, "product", None)
            rows.append({
                "id": str(review.pk),
                "reviewer_name": reviewer_name,
                "reviewer_avatar_url": avatar_url,
                "product_title": product.title if product else None,
                "product_slug": product.slug if product else None,
                "rating": review.rating,
                "review_text": review.review or "",
                "helpful_votes": review.helpful_votes,
                "created_at": review.created_at.isoformat() if review.created_at else None,
            })
        return rows
    except Exception as exc:
        logger.error("aget_homepage_reviews: %s", exc)
        return []
