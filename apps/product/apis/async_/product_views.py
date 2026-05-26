# apps/product/apis/async_/product_views.py
"""
Enterprise Django-Ninja async router for the Product domain.

Architecture principles:
  - All route handlers are async (native Django 6.0 ASGI-first).
  - Reads delegate to selectors (aget_* / afilter_*) — never raw ORM.
  - Mutations call service layer methods (async wrappers).
  - asyncio.gather() is used for the detail bundle endpoint to run
    product + reviews + wishlist queries in parallel.
  - Typed responses use the Pydantic schemas from product_schemas.py.
  - Authentication uses AsyncJWTAuth (Bearer token).
  - Pagination uses the shared async_ninja_paginate utility.
  - Zero N+1 guaranteed via selector prefetch contracts.

────────────────────────────────────────────────────────────────
5 Additional Enterprise Best-Practice Additions (Ninja-specific)
────────────────────────────────────────────────────────────────
1. BUNDLE ENDPOINT: GET /{slug}/bundle/ returns product+reviews+wishlist in
   one parallel asyncio.gather call — single HTTP round-trip for the frontend.
2. WISHLIST BULK CHECK: POST /wishlist/bulk-check/ accepts a list of product
   slugs and returns dict[slug → is_wishlisted] for rendering heart icons.
3. COUPON VALIDATE: POST /coupons/validate/ validates coupon server-side
   before checkout to give real-time discount previews.
4. INVENTORY ADJUST (Async): PATCH /vendor/{slug}/inventory/ runs stock
   mutation through the async service for minimal ASGI event-loop blocking.
5. SEARCH SUGGEST: GET /search/suggest/ returns lightweight slug+title list
   for frontend autocomplete driven by the selector's FTS index.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.common.pagination import async_ninja_paginate
from apps.common.roles import is_client_role, is_vendor_role
from apps.product.schemas.product_schemas import (
    CouponValidateIn,
    CouponValidateOut,
    InventoryAdjustIn,
    ProductDetailBundleOut,
    ProductDetailOut,
    ProductInventoryLogOut,
    ProductListItemOut,
    ProductReviewWriteIn,
    WishlistBulkStatusOut,
    WishlistToggleOut,
)
from apps.product.selectors import (
    aget_product_detail_bundle,
    aget_product_detail,
    aget_vendor_product,
    afilter_products,
    alist_inventory_logs,
    alist_reviews_for_product_slug,
    areviews_for_product,
    asearch_suggest,
    auser_has_wishlist_slug,
    avendor_coupons,
    avendor_products,
    awishlist_for_identity,
    aget_wishlist_status_for_products,
)
from apps.product.services import (
    async_adjust_inventory,
    async_create_review_for_slug,
    async_increment_product_views,
    async_record_product_view,
    async_toggle_wishlist_for_slug,
    async_validate_and_apply_coupon,
)

logger = logging.getLogger(__name__)
router = Router(tags=["Product — Async"])


class WishlistBulkCheckIn(Schema):
    slugs: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# SERIALIZATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _money(value) -> str:
    if value is None:
        return "0.00"
    return f"{Decimal(str(value)):.2f}"


def _url(field) -> str | None:
    if not field:
        return None
    try:
        raw = str(field.url)
        # Inject Cloudinary auto quality/format for any image
        if "res.cloudinary.com" in raw and "/upload/" in raw:
            return raw.replace("/upload/", "/upload/f_auto,q_auto/")
        return raw
    except (AttributeError, ValueError):
        return str(field) if field else None


def _thumbnail_url(field) -> str | None:
    if not field:
        return None
    try:
        raw = str(field.url)
        if "res.cloudinary.com" in raw and "/upload/" in raw:
            return raw.replace("/upload/", "/upload/w_400,h_400,c_fill,f_auto,q_auto/")
        return raw
    except (AttributeError, ValueError):
        return None


def _safe_get(obj, attr, default=None):
    if not obj:
        return default
    # Access __dict__ directly first to bypass descriptor lookup and prevent deferred database reload triggers
    if attr in obj.__dict__:
        val = obj.__dict__[attr]
        if val is not None:
            return val
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def _vendor_out(vendor) -> dict:
    if not vendor:
        return {
            "id": "",
            "store_name": "Fashionistar",
            "slug": None,
            "avatar_url": None,
            "is_verified": False,
        }
    logo = (
        _safe_get(vendor, "logo_url")
        or _safe_get(vendor, "logo")
        or _safe_get(vendor, "avatar")
    )
    return {
        "id": str(vendor.pk),
        "store_name": (
            _safe_get(vendor, "store_name")
            or _safe_get(vendor, "business_name")
            or str(vendor)
        ),
        "slug": _safe_get(vendor, "store_slug") or _safe_get(vendor, "slug"),
        "avatar_url": _url(logo),
        "is_verified": bool(_safe_get(vendor, "is_verified", False)),
    }


def _category_out(cat) -> dict | None:
    if not cat:
        return None
    return {
        "id": str(cat.pk),
        "name": cat.name,
        "slug": cat.slug,
        "image_url": _url(getattr(cat, "image", None)),
    }


def _first_related(manager):
    """Return the first item from a prefetched related manager."""
    try:
        return next(iter(manager.all()), None)
    except Exception:
        return None


def _size_out(size) -> dict:
    return {"id": str(size.pk), "name": size.name}


def _color_out(color) -> dict:
    return {"id": str(color.pk), "name": color.name, "hex_code": color.hex_code or "#000000"}


def _tag_out(tag) -> dict:
    return {"id": str(tag.pk), "name": tag.name, "slug": tag.slug}


def _gallery_item_out(media) -> dict:
    raw_url = _url(media.media)
    return {
        "id": str(media.pk),
        "media_url": raw_url,
        "thumbnail_url": _thumbnail_url(media.media),
        "media_type": media.media_type,
        "alt_text": media.alt_text or "",
        "ordering": media.ordering,
    }


def _variant_out(v) -> dict:
    return {
        "id": str(v.pk),
        "sku": v.sku,
        "size": _size_out(v.size) if v.size else None,
        "color": _color_out(v.color) if v.color else None,
        "price_override": _money(v.price_override) if v.price_override else None,
        "stock_qty": v.stock_qty,
        "is_active": v.is_active,
        "image_url": _url(getattr(v, "image", None)),
    }


def _review_out(review) -> dict:
    user = getattr(review, "user", None)
    profile = None
    if user:
        profile = getattr(user, "client_profile", None) or getattr(user, "vendor_profile", None)
    avatar = getattr(profile, "avatar", None) if profile else None
    reviewer_name = review.reviewer_name or (
        getattr(user, "get_full_name", lambda: "")() if user else None
    ) or "Anonymous"
    return {
        "id": str(review.pk),
        "reviewer_display": reviewer_name,
        "reviewer_avatar_url": _url(avatar),
        "product_title": getattr(getattr(review, "product", None), "title", None),
        "rating": review.rating,
        "review": review.review,
        "reply": review.reply or "",
        "helpful_votes": review.helpful_votes,
        "active": review.active,
        "moderated": review.moderated,
        "created_at": review.created_at,
    }


def _product_card_out(product) -> dict:
    """
    Compact card serialization. Only accesses columns included in the selector's
    .only() projection and prefetched M2M relations — zero extra queries.
    """
    raw_url = _url(product.image)
    # ── Async-safe category read ──────────────────────────────────────────────
    # Do NOT call product.primary_category (@property) — it fires a sync ORM
    # query (list(self.categories.all()[:1])) which raises SynchronousOnlyOperation
    # in Django Ninja async context.
    # Instead, read from the prefetch cache populated by the selector's
    # prefetch_related("product__categories"). This is zero-query and async-safe.
    prefetch_cache = getattr(product, "_prefetched_objects_cache", {}) or {}
    prefetched_cats = prefetch_cache.get("categories", None)
    if prefetched_cats is not None:
        category = prefetched_cats[0] if prefetched_cats else None
    else:
        # Fallback: _first_related reads from the M2M manager — only safe in
        # sync DRF context. For async Ninja the prefetch_related above ensures
        # this branch is never reached.
        category = _first_related(product.categories)
    # Inject Cloudinary card-size transform
    card_url = None
    if raw_url and "res.cloudinary.com" in raw_url:
        card_url = raw_url.replace(
            "/upload/", "/upload/w_480,h_480,c_fill,f_auto,q_auto/"
        )
    else:
        card_url = raw_url

    prefetched_cache = getattr(product, "_prefetched_objects_cache", {}) or {}
    prefetched_sizes = getattr(product, "_prefetched_sizes", None)
    prefetched_colors = getattr(product, "_prefetched_colors", None)
    sizes = (
        prefetched_sizes
        if prefetched_sizes is not None
        else list(prefetched_cache.get("sizes", []))
    )
    colors = (
        prefetched_colors
        if prefetched_colors is not None
        else list(prefetched_cache.get("colors", []))
    )

    return {
        "id": str(product.pk),
        "title": product.title,
        "slug": product.slug,
        "sku": product.sku,
        "price": _money(product.price),
        "old_price": _money(product.old_price) if product.old_price else None,
        "discount_percentage": getattr(product, "discount_percentage", 0),
        "currency": product.currency,
        "image_url": card_url,
        "in_stock": product.in_stock,
        "stock_qty": product.stock_qty,
        "featured": product.featured,
        "hot_deal": product.hot_deal,
        "digital": product.digital,
        "rating": float(product.rating or 0),
        "review_count": product.review_count,
        "computed_review_count": getattr(product, "computed_review_count", 0),
        "computed_avg_rating": getattr(product, "computed_avg_rating", 0.0),
        "category_name": category.name if category else None,
        "category_slug": category.slug if category else None,
        "brand_name": None,
        "brand_slug": None,
        "vendor_name": _vendor_out(product.vendor)["store_name"],
        "vendor_slug": _vendor_out(product.vendor)["slug"],
        "requires_measurement": product.requires_measurement,
        "is_customisable": product.is_customisable,
        "sizes": [_size_out(s) for s in sizes],
        "colors": [_color_out(c) for c in colors],
        "created_at": product.created_at,
    }


def _product_detail_out(product) -> dict:
    """Full product detail including gallery, variants, specs, FAQs."""
    card = _product_card_out(product)
    prefetched_cache = getattr(product, "_prefetched_objects_cache", {}) or {}
    prefetched_variants = list(prefetched_cache.get("product_variants", []))
    card.update(
        {
            "description": product.description or "",
            "short_description": getattr(product, "short_description", "") or "",
            "shipping_amount": _money(product.shipping_amount),
            "cover_image_url": card.get("image_url"),
            "gallery": [
                _gallery_item_out(m)
                for m in product.product_gallery_media.all()
                if not getattr(m, "is_deleted", False)
            ],
            "max_stock": getattr(product, "max_stock", None),
            "views": product.views,
            "orders_count": product.orders_count,
            "sub_category_name": (
                product.primary_sub_category.name
                if getattr(product, "primary_sub_category", None)
                else None
            ),
            "tags": [_tag_out(t) for t in product.tags.all()],
            "specifications": [
                {
                    "id": str(s.pk),
                    "title": s.specification_title,
                    "content": s.specification_value,
                }
                for s in product.product_specifications.all()
            ],
            "faqs": [
                {"id": str(f.pk), "question": f.question, "answer": f.answer}
                for f in product.product_faqs.all()
            ],
            "variants": [
                _variant_out(v)
                for v in prefetched_variants
                if getattr(v, "is_active", False)
            ],
            "status": product.status,
            "vendor": _vendor_out(product.vendor),
            "vendor_id": str(product.vendor.pk) if product.vendor else None,
            "vendor_name": _vendor_out(product.vendor)["store_name"],
            "vendor_slug": _vendor_out(product.vendor)["slug"],
            "vendor_is_verified": _vendor_out(product.vendor)["is_verified"],
            "commission_rate": _money(product.commission_rate),
            "updated_at": product.updated_at,
        }
    )
    return card


# ─────────────────────────────────────────────────────────────────────────────
# AUTH GUARDS
# ─────────────────────────────────────────────────────────────────────────────

def _require_auth(request) -> Any:
    user = getattr(request, "auth", None)
    if not user:
        raise HttpError(401, "Authentication required.")
    return user


def _require_client(request) -> Any:
    user = _require_auth(request)
    if not is_client_role(getattr(user, "role", None)):
        raise HttpError(403, "Client access required.")
    return user


async def _require_vendor(request) -> Any:
    user = _require_auth(request)
    if not is_vendor_role(getattr(user, "role", None)):
        raise HttpError(403, "Vendor access required.")
    try:
        profile = user.vendor_profile
    except (AttributeError, ObjectDoesNotExist):
        profile = None
    if not profile:
        raise HttpError(403, "Vendor profile not found.")
    return profile


async def _resolve_optional_bearer_user(request) -> Any | None:
    """Hydrate an optional JWT bearer user for public-friendly reads."""

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        from backend.ninja_api import AsyncJWTAuth

        return await AsyncJWTAuth().authenticate(request, token)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# PAGINATION HELPER
# ─────────────────────────────────────────────────────────────────────────────

async def _paginated(request, qs, serializer_fn, *, page: int = 1, page_size: int = 24) -> dict:
    """Async-paginate a queryset and apply serializer_fn to each item."""
    page_size = min(page_size, 100)
    payload = await async_ninja_paginate(
        request, qs, page=page, page_size=page_size, max_page_size=100
    )
    payload["results"] = [serializer_fn(item) for item in payload["results"]]
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC — List / Featured / Search
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/", auth=None, summary="List all published products")
async def list_products(
    request,
    page: int = 1,
    page_size: int = 24,
    q: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    vendor: str | None = None,
    in_stock: bool | None = None,
    featured: bool | None = None,
    min_price: str | None = None,
    max_price: str | None = None,
    ordering: str = "-created_at",
):
    SAFE_ORDERING = {"-created_at", "price", "-price", "rating", "latest", "popular"}
    if ordering not in SAFE_ORDERING:
        ordering = "-created_at"
    qs = afilter_products(
        query=q,
        category=category,
        brand=brand,
        vendor=vendor,
        in_stock=in_stock,
        featured=featured,
        min_price=min_price,
        max_price=max_price,
        ordering=ordering,
    )
    return await _paginated(request, qs, _product_card_out, page=page, page_size=page_size)


@router.get("/featured/", auth=None, summary="List featured products")
async def list_featured_products(request, page: int = 1, page_size: int = 20):
    qs = afilter_products(featured=True, ordering="latest")
    return await _paginated(request, qs, _product_card_out, page=page, page_size=page_size)


@router.get("/search/suggest/", auth=None, summary="Autocomplete product titles")
async def search_suggest(request, q: str = ""):
    """
    Best-practice #5: lightweight FTS suggest for frontend autocomplete.
    Returns [{slug, title}] — no images, no heavy fields.
    """
    if len(q.strip()) < 2:
        return {"results": []}
    suggestions = await asearch_suggest(q.strip())
    return {
        "results": [
            {"slug": s.slug, "title": s.title}
            for s in suggestions
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# STATIC ROUTES — Must ALL be registered BEFORE /{slug}/ wildcard.
# Django Ninja evaluates routes in registration order; /{slug}/ would
# otherwise swallow /wishlist/, /coupons/validate/ etc. as product slugs.
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/wishlist/", auth=None, summary="List user or anonymous wishlist")
async def list_wishlist(
    request,
    page: int = 1,
    page_size: int = 24,
    session_key: str | None = None,
):
    session_key = (
        session_key
        or request.headers.get("X-Fashionistar-Session-Key")
        or request.COOKIES.get("fashionistar_session_key")
    )
    user = await _resolve_optional_bearer_user(request)
    if user is not None:
        request.auth = user
    if user:
        qs = awishlist_for_identity(user_id=user.pk)
    else:
        qs = awishlist_for_identity(session_key=session_key)
    return await _paginated(
        request, qs,
        lambda item: {
            "id": str(item.pk),
            "product": _product_card_out(item.product),
            "created_at": item.created_at,
        },
        page=page, page_size=page_size,
    )


@router.post("/wishlist/bulk-check/", summary="Bulk wishlist status for product list")
async def bulk_wishlist_check(request, payload: WishlistBulkCheckIn):
    """
    Best-practice #2: accepts list of product slugs, returns dict of
    slug → is_wishlisted. Used to render heart icons on catalog cards.
    """
    slugs = payload.slugs
    user = await _resolve_optional_bearer_user(request)
    if user is not None:
        request.auth = user
    if not user:
        return {"statuses": {slug: False for slug in slugs}}
    statuses = await aget_wishlist_status_for_products(user.pk, slugs)
    return {"statuses": statuses}


@router.post("/coupons/validate/", summary="Validate coupon before checkout")
async def validate_coupon_async_static(request, payload: "CouponValidateIn"):
    """
    Static route registration placeholder — real handler defined below.
    This entry ensures route is matched before /{slug}/ wildcard.
    See validate_coupon_async for implementation.
    """
    # Actual logic is in the named handler below — this duplicate
    # registration is intentional to fix ordering. Django Ninja
    # will use the last registered handler for a duplicate path.
    from apps.product.selectors.product_selectors import validate_coupon  # noqa
    try:
        result = await validate_coupon(payload.code, payload.cart_total)
    except Exception as exc:  # noqa: BLE001
        raise HttpError(400, str(exc))
    return result


@router.get("/{slug}/", auth=None, summary="Get product detail by slug")
async def get_product(request, slug: str):
    try:
        product = await aget_product_detail(slug)
        if not product:
            raise HttpError(404, "Product not found.")
        await async_increment_product_views(product.pk)
        return _product_detail_out(product)
    except asyncio.CancelledError:
        logger.debug("Request for product slug=%s cancelled by client", slug)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC — Bundle (Best-practice #1)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{slug}/bundle/", auth=None, summary="Parallel bundle: product + reviews + wishlist")
async def get_product_bundle(request, slug: str):
    """
    Best-practice #1: single endpoint that fetches product + reviews +
    wishlist status in one asyncio.gather() call.
    The frontend makes one HTTP request and gets everything for the PDP.
    """
    user = await _resolve_optional_bearer_user(request)
    if user is not None:
        request.auth = user

    try:
        product, reviews, in_wishlist = await asyncio.gather(
            aget_product_detail(slug),
            alist_reviews_for_product_slug(slug, limit=20),
            auser_has_wishlist_slug(user, slug),
        )
    except asyncio.CancelledError:
        logger.debug("Request for product bundle slug=%s cancelled by client", slug)
        raise

    if not product:
        raise HttpError(404, "Product not found.")

    review_list = [_review_out(r) for r in reviews]
    avg = (
        sum(r["rating"] for r in review_list) / len(review_list)
        if review_list else 0.0
    )
    return {
        "product": _product_detail_out(product),
        "reviews": review_list,
        "in_wishlist": in_wishlist,
        "review_count": len(review_list),
        "avg_rating": round(avg, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT — Reviews
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{slug}/reviews/", auth=None, summary="List product reviews")
async def list_product_reviews(
    request, slug: str, page: int = 1, page_size: int = 10
):
    product = await aget_product_detail(slug)
    if not product:
        raise HttpError(404, "Product not found.")
    qs = areviews_for_product(product.pk)
    return await _paginated(request, qs, _review_out, page=page, page_size=page_size)


@router.post("/{slug}/reviews/", summary="Submit product review")
async def create_product_review(request, slug: str, payload: ProductReviewWriteIn):
    user = _require_client(request)
    try:
        review = await async_create_review_for_slug(
            user=user,
            slug=slug,
            rating=payload.rating,
            review_text=payload.review,
            idempotency_key=payload.idempotency_key,
        )
    except ObjectDoesNotExist:
        raise HttpError(404, "Product not found.")
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return _review_out(review)


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT — Wishlist (slug-parameterized routes — registered AFTER static ones)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{slug}/wishlist/toggle/", summary="Toggle wishlist (add/remove)")
async def toggle_wishlist_async(request, slug: str):
    """Returns {added: bool, message: str}."""
    user = _require_client(request)
    try:
        result = await async_toggle_wishlist_for_slug(user=user, slug=slug)
    except ObjectDoesNotExist:
        raise HttpError(404, "Product not found.")
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return {
        "added": result["added"],
        "message": "Added to wishlist." if result["added"] else "Removed from wishlist.",
    }


# bulk_wishlist_check and list_wishlist moved above /{slug}/ — see static section above


# ─────────────────────────────────────────────────────────────────────────────
# COUPON VALIDATE  (Best-practice #3)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/coupons/validate/", summary="Validate coupon before checkout")
async def validate_coupon_async(request, payload: CouponValidateIn):
    """
    Best-practice #3: real-time coupon validation for the checkout page.
    Returns discount details without consuming the coupon usage count.
    """
    user = _require_auth(request)
    try:
        result = await async_validate_and_apply_coupon(
            code=payload.code,
            user=user,
            order_subtotal=payload.order_subtotal,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR — Products
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/vendor/", summary="List vendor's own products")
async def list_vendor_products(request, page: int = 1, page_size: int = 24):
    profile = await _require_vendor(request)
    qs = avendor_products(profile.pk)
    return await _paginated(request, qs, _product_card_out, page=page, page_size=page_size)


@router.get("/vendor/{slug}/", summary="Get vendor product detail")
async def get_vendor_product_detail(request, slug: str):
    profile = await _require_vendor(request)
    product = await aget_vendor_product(profile.pk, slug)
    if not product:
        raise HttpError(404, "Product not found.")
    return _product_detail_out(product)


@router.get("/vendor/{slug}/media/", summary="List vendor product gallery")
async def list_vendor_gallery(request, slug: str):
    profile = await _require_vendor(request)
    product = await aget_vendor_product(profile.pk, slug)
    if not product:
        raise HttpError(404, "Product not found.")
    items = [
        _gallery_item_out(m)
        for m in product.product_gallery_media.all()
        if not getattr(m, "is_deleted", False)
    ]
    return {"count": len(items), "results": items}


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR — Inventory  (Best-practice #4)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/vendor/{slug}/inventory/", summary="List stock movement history")
async def list_inventory_logs(request, slug: str, page: int = 1, page_size: int = 20):
    """Best-practice #4: async inventory log read."""
    profile = await _require_vendor(request)
    product = await aget_vendor_product(profile.pk, slug)
    if not product:
        raise HttpError(404, "Product not found.")
    qs = alist_inventory_logs(product.pk)
    return await _paginated(
        request, qs,
        lambda log: {
            "id": str(log.pk),
            "quantity_delta": log.quantity_delta,
            "quantity_before": log.quantity_before,
            "quantity_after": log.quantity_after,
            "reason": log.reason,
            "reference_id": log.reference_id or "",
            "note": log.note or "",
            "actor_name": (
                getattr(log.actor, "get_full_name", lambda: "System")()
                if log.actor else "System"
            ),
            "created_at": log.created_at,
        },
        page=page, page_size=page_size,
    )


@router.patch("/vendor/{slug}/inventory/", summary="Adjust product stock")
async def adjust_inventory_async(request, slug: str, payload: InventoryAdjustIn):
    profile = await _require_vendor(request)
    product = await aget_vendor_product(profile.pk, slug)
    if not product:
        raise HttpError(404, "Product not found.")
    try:
        log = await async_adjust_inventory(
            product=product,
            quantity_delta=payload.quantity_delta,
            reason=payload.reason,
            actor=request.auth,
            note=payload.note,
            reference_id=payload.reference_id,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return {
        "id": str(log.pk),
        "quantity_after": log.quantity_after,
        "message": f"Stock adjusted by {payload.quantity_delta:+d} units.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR — Coupons
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/coupons/", summary="List vendor coupons")
async def list_vendor_coupons(request, page: int = 1, page_size: int = 20):
    profile = await _require_vendor(request)
    qs = avendor_coupons(profile.pk)

    def _coupon_out(c):
        return {
            "id": str(c.pk),
            "code": c.code,
            "discount_type": c.discount_type,
            "discount_value": _money(c.discount_value),
            "minimum_order": _money(c.minimum_order),
            "usage_limit": c.usage_limit,
            "usage_count": c.usage_count,
            "active": c.active,
            "valid_from": c.valid_from,
            "valid_to": c.valid_to,
        }

    return await _paginated(request, qs, _coupon_out, page=page, page_size=page_size)


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS — View Log  (Phase 1 — 2026)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{slug}/view-log/", auth=None, summary="Record product view for recommendation engine")
async def record_product_view(
    request,
    slug: str,
    session_key: str | None = None,
    referrer_url: str | None = None,
    device_type: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
):
    """
    Phase 1 — Analytics event endpoint.

    Written asynchronously on every PDP view by the frontend.
    The client MUST fire-and-forget (never await critical code on this).

    Privacy guarantees:
        - No IP address is stored.
        - Authenticated user FK is SET_NULL on account deletion.
        - Anonymous users tracked by session_key only (40-char Django session key).
        - All UTM params are optional — if absent, stored as empty strings.

    Failure policy:
        - This endpoint NEVER returns a 4xx/5xx to the frontend.
        - Any DB error is caught and logged server-side.
        - Returns 200 {logged: false, reason: "..."} on failure.

    Best practice: increment Product.views count atomically here too.
    """
    try:
        result = await async_record_product_view(
            slug=slug,
            user=getattr(request, "auth", None),
            session_key=session_key,
            referrer_url=referrer_url,
            device_type=device_type,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
        )
        logger.debug("ViewLog attempted: product=%s result=%s", slug, result)
        return result

    except Exception as exc:
        logger.warning("ViewLog write failed for slug=%s: %s", slug, exc, exc_info=False)
        return {"logged": False, "reason": "write_error"}
