# apps/product/selectors/product_selectors.py
"""
Read-only query functions for the Product domain.

All selectors return QuerySets and are composable.
Views call selectors — never raw ORM — to centralize query logic.
"""

import logging
from django.db.models import Avg, Count, Q

from apps.product.models import (
    Product,
    ProductReview,
    ProductWishlist,
    ProductStatus,
    Coupon,
)
from apps.common.selectors import BaseSelector

logger = logging.getLogger(__name__)


class ProductSelector(BaseSelector):
    """Product read selector namespace for sync DRF and async Ninja reads."""

    model = Product


# ─────────────────────────────────────────────────────────────────────────────
# 1. PRODUCT QUERYSETS
# ─────────────────────────────────────────────────────────────────────────────

def get_published_products():
    """Base published queryset with common select/prefetch."""
    return (
        Product.objects.filter(status=ProductStatus.PUBLISHED, is_deleted=False)
        .select_related("vendor", "vendor__user", "category", "brand")
        .prefetch_related("sizes", "colors", "tags", "gallery")
        .order_by("-created_at")
    )


def get_product_detail(slug: str) -> Product | None:
    """Full product detail for a single slug — includes specs, FAQs, variants."""
    try:
        return (
            Product.objects.filter(status=ProductStatus.PUBLISHED, is_deleted=False, slug=slug)
            .select_related("vendor", "vendor__user", "category", "sub_category", "brand")
            .prefetch_related(
                "sizes", "colors", "tags",
                "gallery", "variants__size", "variants__color",
                "specifications", "faqs",
            )
            .get()
        )
    except Product.DoesNotExist:
        return None


def get_featured_products(limit: int = 20):
    return get_published_products().filter(featured=True)[:limit]


def get_products_by_category(category_id):
    return get_published_products().filter(
        Q(category_id=category_id) | Q(sub_category_id=category_id)
    )


def get_products_by_vendor(vendor_id):
    return (
        Product.objects.filter(vendor_id=vendor_id, is_deleted=False)
        .select_related("vendor", "vendor__user", "category", "brand")
        .prefetch_related("sizes", "colors", "gallery")
        .order_by("-created_at")
    )


def get_vendor_product_or_404(vendor_id, slug: str) -> Product | None:
    try:
        return Product.objects.filter(
            vendor_id=vendor_id, slug=slug, is_deleted=False
        ).get()
    except Product.DoesNotExist:
        return None


def search_products(query: str):
    """Full-text + icontains fallback search."""
    if not query:
        return get_published_products()
    return (
        get_published_products()
        .filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(sku__icontains=query) |
            Q(tags__name__icontains=query)
        )
        .distinct()
    )


def filter_products(
    *,
    category_id=None,
    brand_id=None,
    min_price=None,
    max_price=None,
    in_stock=None,
    featured=None,
    size_ids=None,
    color_ids=None,
    query=None,
):
    qs = get_published_products()
    if query:
        qs = qs.filter(
            Q(title__icontains=query) | Q(sku__icontains=query) | Q(tags__name__icontains=query)
        ).distinct()
    if category_id:
        qs = qs.filter(Q(category_id=category_id) | Q(sub_category_id=category_id))
    if brand_id:
        qs = qs.filter(brand_id=brand_id)
    if min_price is not None:
        qs = qs.filter(price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(price__lte=max_price)
    if in_stock is not None:
        qs = qs.filter(in_stock=in_stock)
    if featured is not None:
        qs = qs.filter(featured=featured)
    if size_ids:
        qs = qs.filter(sizes__id__in=size_ids).distinct()
    if color_ids:
        qs = qs.filter(colors__id__in=color_ids).distinct()
    return qs


# ─────────────────────────────────────────────────────────────────────────────
# 2. REVIEW QUERYSETS
# ─────────────────────────────────────────────────────────────────────────────

def get_product_reviews(product_id):
    return (
        ProductReview.objects.filter(product_id=product_id, active=True)
        .order_by("-created_at")
    )


def get_user_review_for_product(user_id, product_id) -> ProductReview | None:
    try:
        return ProductReview.objects.get(user_id=user_id, product_id=product_id)
    except ProductReview.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. WISHLIST QUERYSETS
# ─────────────────────────────────────────────────────────────────────────────

def get_user_wishlist(user_id):
    return (
        ProductWishlist.objects.filter(user_id=user_id)
        .select_related("product__category", "product__brand", "product__vendor")
        .prefetch_related("product__gallery")
        .order_by("-created_at")
    )


def is_in_wishlist(user_id, product_id) -> bool:
    return ProductWishlist.objects.filter(
        user_id=user_id, product_id=product_id
    ).exists()


# ─────────────────────────────────────────────────────────────────────────────
# 4. COUPON QUERYSETS
# ─────────────────────────────────────────────────────────────────────────────

def get_vendor_coupons(vendor_id):
    return (
        Coupon.objects.filter(vendor_id=vendor_id, is_deleted=False)
        .order_by("-created_at")
    )


def get_coupon_by_code(code: str) -> Coupon | None:
    try:
        return Coupon.objects.get(code__iexact=code.strip(), is_deleted=False)
    except Coupon.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 5. ASYNC QUERYSETS FOR DJANGO-NINJA READS
# ─────────────────────────────────────────────────────────────────────────────

def afilter_products(
    *,
    category: str | None = None,
    brand: str | None = None,
    min_price=None,
    max_price=None,
    in_stock: bool | None = None,
    featured: bool | None = None,
    query: str | None = None,
    ordering: str = "-created_at",
):
    """Return an async-ready published product queryset for Ninja feeds."""

    qs = filter_products(
        category_id=category,
        brand_id=brand,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        featured=featured,
        query=query,
    )
    allowed_ordering = {
        "price": "price",
        "-price": "-price",
        "latest": "-created_at",
        "oldest": "created_at",
        "rating": "-rating",
        "-created_at": "-created_at",
    }
    return qs.order_by(allowed_ordering.get(ordering, "-created_at"))


async def aget_product_detail(slug: str) -> Product | None:
    """Async: return full public product detail by slug, or None."""

    try:
        return await (
            Product.objects.filter(
                status=ProductStatus.PUBLISHED,
                is_deleted=False,
                slug=slug,
            )
            .select_related("vendor", "vendor__user", "category", "sub_category", "brand")
            .prefetch_related(
                "sizes",
                "colors",
                "tags",
                "gallery",
                "variants__size",
                "variants__color",
                "specifications",
                "faqs",
            )
            .aget()
        )
    except Product.DoesNotExist:
        return None


def areviews_for_product(product_id):
    """Return an async-ready active reviews queryset for a product."""

    return get_product_reviews(product_id)


def awishlist_for_user(user_id):
    """Return an async-ready wishlist queryset for one user."""

    return get_user_wishlist(user_id)


def avendor_coupons(vendor_id):
    """Return an async-ready coupon queryset for one vendor."""

    return get_vendor_coupons(vendor_id)


def avendor_products(vendor_id):
    """Return an async-ready product queryset for one vendor profile."""

    return (
        Product.objects.filter(vendor_id=vendor_id, is_deleted=False)
        .select_related("vendor", "vendor__user", "category", "brand")
        .prefetch_related("sizes", "colors", "tags", "gallery")
        .order_by("-created_at")
    )


async def aget_vendor_product(vendor_id, slug: str) -> Product | None:
    """Async: return one product owned by a vendor profile, or None."""

    try:
        return await (
            Product.objects.filter(vendor_id=vendor_id, slug=slug, is_deleted=False)
            .select_related("vendor", "vendor__user", "category", "sub_category", "brand")
            .prefetch_related(
                "sizes",
                "colors",
                "tags",
                "gallery",
                "variants__size",
                "variants__color",
                "specifications",
                "faqs",
            )
            .aget()
        )
    except Product.DoesNotExist:
        return None
