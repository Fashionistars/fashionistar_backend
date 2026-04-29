"""Product Django-Ninja async read router."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from ninja import Router
from ninja.errors import HttpError

from apps.common.pagination import async_ninja_paginate
from apps.common.roles import is_client_role, is_vendor_role
from apps.product.schemas import (
    ProductDetailOut,
)
from apps.product.selectors import (
    aget_product_detail,
    aget_vendor_product,
    afilter_products,
    areviews_for_product,
    avendor_coupons,
    avendor_products,
    awishlist_for_user,
)

router = Router(tags=["Product — Async Reads"])


def _money(value) -> str:
    """Return decimal-compatible values as stable frontend strings."""

    if value is None:
        return "0.00"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def _media_url(value) -> str | None:
    """Return a Cloudinary-backed secure URL when available."""

    if not value:
        return None
    try:
        return str(value.url)
    except (AttributeError, ValueError):
        return str(value) if value else None


def _size_out(size) -> dict:
    """Serialize product size for frontend contracts."""

    return {
        "id": str(size.pk),
        "name": size.name,
        "abbreviation": size.name,
        "sort_order": 0,
    }


def _color_out(color) -> dict:
    """Serialize product color for frontend contracts."""

    return {
        "id": str(color.pk),
        "name": color.name,
        "hex_code": color.hex_code or "#000000",
    }


def _category_out(category) -> dict:
    """Serialize a nullable product category."""

    if not category:
        return {"id": "", "name": "Uncategorized", "slug": ""}
    return {
        "id": str(category.pk),
        "name": getattr(category, "name", "") or "Uncategorized",
        "slug": getattr(category, "slug", "") or "",
    }


def _vendor_out(vendor) -> dict:
    """Serialize a nullable vendor profile."""

    if not vendor:
        return {"id": "", "store_name": "Fashionistar", "slug": "", "avatar_url": None}
    return {
        "id": str(vendor.pk),
        "store_name": vendor.store_name or str(vendor),
        "slug": vendor.store_slug or "",
        "avatar_url": _media_url(getattr(getattr(vendor, "user", None), "avatar", None)),
    }


def _brand_out(brand) -> dict | None:
    """Serialize a nullable product brand."""

    if not brand:
        return None
    return {
        "id": str(brand.pk),
        "name": getattr(brand, "title", "") or "",
        "slug": getattr(brand, "slug", "") or "",
        "logo_url": _media_url(getattr(brand, "image", None)),
    }


def _product_list_out(product) -> dict:
    """Serialize the compact product card payload."""

    return {
        "id": str(product.pk),
        "slug": product.slug,
        "title": product.title,
        "sku": product.sku,
        "cover_image_url": _media_url(product.image),
        "price": _money(product.price),
        "old_price": _money(product.old_price) if product.old_price else None,
        "currency": product.currency,
        "average_rating": float(product.rating or 0),
        "review_count": product.review_count,
        "requires_measurement": product.requires_measurement,
        "status": product.status,
        "is_featured": product.featured,
        "vendor": _vendor_out(product.vendor),
        "category": _category_out(product.category),
    }


def _product_detail_out(product) -> dict:
    """Serialize the full product detail payload."""

    payload = _product_list_out(product)
    payload.update(
        {
            "description": product.description,
            "condition": "new",
            "weight_kg": None,
            "brand": _brand_out(product.brand),
            "tags": [
                {"id": str(tag.pk), "name": tag.name, "slug": tag.slug}
                for tag in product.tags.all()
            ],
            "sizes": [_size_out(size) for size in product.sizes.all()],
            "colors": [_color_out(color) for color in product.colors.all()],
            "gallery": [
                {
                    "id": str(media.pk),
                    "image_url": _media_url(media.media) or "",
                    "media_type": media.media_type,
                    "alt_text": media.alt_text,
                    "ordering": media.ordering,
                }
                for media in product.gallery.all()
                if not getattr(media, "is_deleted", False)
            ],
            "variants": [
                {
                    "id": str(variant.pk),
                    "sku": variant.sku,
                    "size": _size_out(variant.size) if variant.size else None,
                    "color": _color_out(variant.color) if variant.color else None,
                    "price_override": (
                        _money(variant.price_override) if variant.price_override else None
                    ),
                    "stock": variant.stock_qty,
                    "is_active": variant.is_active,
                }
                for variant in product.variants.all()
            ],
            "specifications": [
                {"label": spec.title, "value": spec.content}
                for spec in product.specifications.all()
            ],
            "faqs": [
                {"question": faq.question, "answer": faq.answer}
                for faq in product.faqs.all()
            ],
            "commission_rate": _money(product.commission_rate),
            "stock_count": product.stock_qty,
            "views_count": product.views,
            "published_at": product.updated_at if product.status == "published" else None,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }
    )
    return payload


def _review_out(review) -> dict:
    """Serialize one product review."""

    return {
        "id": str(review.pk),
        "reviewer_name": review.reviewer_name or "Anonymous",
        "reviewer_avatar": None,
        "rating": review.rating,
        "comment": review.review,
        "vendor_reply": review.reply or None,
        "helpful_count": review.helpful_votes,
        "is_verified_purchase": False,
        "created_at": review.created_at,
    }


def _coupon_out(coupon) -> dict:
    """Serialize one vendor coupon."""

    return {
        "id": str(coupon.pk),
        "code": coupon.code,
        "coupon_type": coupon.discount_type,
        "discount_value": _money(coupon.discount_value),
        "min_order_amount": _money(coupon.minimum_order),
        "max_uses": coupon.usage_limit,
        "uses_count": coupon.usage_count,
        "valid_from": coupon.valid_from,
        "valid_until": coupon.valid_to,
        "is_active": coupon.active,
    }


def _require_client_user(request):
    """Return request.auth when the JWT belongs to a client account."""

    user = request.auth
    if user is None or not is_client_role(getattr(user, "role", None)):
        raise HttpError(403, "Client access is required for this endpoint.")
    return user


async def _require_vendor_profile(request):
    """Return the request-auth vendor profile hydrated by AsyncJWTAuth."""

    user = request.auth
    if user is None or not is_vendor_role(getattr(user, "role", None)):
        raise HttpError(403, "Vendor access is required for this endpoint.")

    try:
        profile = user.vendor_profile
    except (AttributeError, ObjectDoesNotExist):
        profile = None

    if profile is None:
        raise HttpError(403, "Vendor setup is required before accessing this endpoint.")
    return profile


async def _paginated(request, queryset, serializer, *, page: int, page_size: int) -> dict:
    """Apply global async Ninja pagination and serialize result objects."""

    payload = await async_ninja_paginate(
        request,
        queryset,
        page=page,
        page_size=page_size,
        max_page_size=25,
    )
    payload["results"] = [serializer(item) for item in payload["results"]]
    return payload


@router.get("/", auth=None)
async def list_products(
    request,
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    brand: str | None = None,
    search: str | None = None,
    ordering: str = "latest",
    is_featured: bool | None = None,
):
    """Return the public product feed."""

    queryset = afilter_products(
        category=category,
        brand=brand,
        query=search,
        featured=is_featured,
        ordering=ordering,
    )
    return await _paginated(
        request,
        queryset,
        _product_list_out,
        page=page,
        page_size=page_size,
    )


@router.get("/featured/", auth=None)
async def list_featured_products(request, page: int = 1, page_size: int = 20):
    """Return featured public products."""

    queryset = afilter_products(featured=True, ordering="latest")
    return await _paginated(
        request,
        queryset,
        _product_list_out,
        page=page,
        page_size=page_size,
    )


@router.get("/wishlist/")
async def list_wishlist(request, page: int = 1, page_size: int = 20):
    """Return the authenticated client's wishlist."""

    user = _require_client_user(request)
    return await _paginated(
        request,
        awishlist_for_user(user.pk),
        lambda item: {
            "id": str(item.pk),
            "product": _product_list_out(item.product),
            "created_at": item.created_at,
        },
        page=page,
        page_size=page_size,
    )


@router.get("/coupons/")
async def list_vendor_coupons(request, page: int = 1, page_size: int = 20):
    """Return coupons owned by the authenticated vendor profile."""

    profile = await _require_vendor_profile(request)
    return await _paginated(
        request,
        avendor_coupons(profile.pk),
        _coupon_out,
        page=page,
        page_size=page_size,
    )


@router.get("/vendor/")
async def list_vendor_products(request, page: int = 1, page_size: int = 20):
    """Return products owned by the authenticated vendor profile."""

    profile = await _require_vendor_profile(request)
    return await _paginated(
        request,
        avendor_products(profile.pk),
        _product_list_out,
        page=page,
        page_size=page_size,
    )


@router.get("/vendor/{slug}/", response=ProductDetailOut)
async def get_vendor_product_detail(request, slug: str):
    """Return one product owned by the authenticated vendor profile."""

    profile = await _require_vendor_profile(request)
    product = await aget_vendor_product(profile.pk, slug)
    if product is None:
        raise HttpError(404, "Product not found.")
    return _product_detail_out(product)


@router.get("/vendor/{slug}/media/")
async def list_vendor_product_media(request, slug: str):
    """Return gallery media for one authenticated vendor product."""

    profile = await _require_vendor_profile(request)
    product = await aget_vendor_product(profile.pk, slug)
    if product is None:
        raise HttpError(404, "Product not found.")
    media_items = [
        media for media in product.gallery.all()
        if not getattr(media, "is_deleted", False)
    ][:25]
    return {
        "count": len(media_items),
        "next": None,
        "previous": None,
        "results": [
            {
                "id": str(media.pk),
                "image_url": _media_url(media.media) or "",
                "media_type": media.media_type,
                "alt_text": media.alt_text,
                "ordering": media.ordering,
            }
            for media in media_items
        ],
    }


@router.get("/{slug}/reviews/", auth=None)
async def list_product_reviews(request, slug: str, page: int = 1, page_size: int = 20):
    """Return active reviews for a public product."""

    product = await aget_product_detail(slug)
    if product is None:
        raise HttpError(404, "Product not found.")
    return await _paginated(
        request,
        areviews_for_product(product.pk),
        _review_out,
        page=page,
        page_size=page_size,
    )


@router.get("/{slug}/", response=ProductDetailOut, auth=None)
async def get_product_detail(request, slug: str):
    """Return one public product detail by slug."""

    product = await aget_product_detail(slug)
    if product is None:
        raise HttpError(404, "Product not found.")
    return _product_detail_out(product)
