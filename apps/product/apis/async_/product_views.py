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
    VendorMeasurementTemplateOut,
    VendorMeasurementTemplateIn,
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


def _public_id(field) -> str | None:
    if not field:
        return None
    return getattr(field, "public_id", None) or str(field)


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
    return {"id": str(size.pk), "name": getattr(size, "size_label", "")}


def _color_out(color) -> dict:
    return {"id": str(color.pk), "name": color.name, "hex_code": color.hex_code or "#000000"}


def _tag_out(tag) -> dict:
    return {"id": str(tag.pk), "name": tag.name, "slug": tag.slug}


def _category_out(category) -> dict:
    image = getattr(category, "image", None)
    image_url = _url(image)
    return {
        "id": str(category.pk),
        "name": category.name,
        "slug": category.slug,
        "image_url": image_url,
    }


def _gallery_item_out(media) -> dict:
    raw_url = _url(media.media)
    return {
        "id": str(media.pk),
        "public_id": _public_id(media.media),
        "media_url": raw_url,
        "thumbnail_url": _thumbnail_url(media.media),
        "media_type": media.media_type,
        "alt_text": media.alt_text or "",
        "ordering": media.ordering,
        "size_id": str(media.size_id) if media.size_id else None,
        "color_name": media.color_name or "",
        "color_hex": media.color_hex or "",
        "sku": media.sku or "",
        "barcode": media.barcode or "",
        "is_primary": media.is_primary,
        "video_thumbnail_url": _url(media.video_thumbnail),
        "duration_sec": media.duration_sec,
    }


def _variant_out(v) -> dict:
    return {
        "id": str(v.pk),
        "public_id": _public_id(v.media),
        "sku": v.sku or "",
        "size": _size_out(v.size) if v.size else None,
        "color_name": v.color_name or "",
        "color_hex": v.color_hex or "",
        "media_type": v.media_type,
        "media_url": _url(v.media),
        "thumbnail_url": _thumbnail_url(v.media),
        "video_thumbnail_url": _url(v.video_thumbnail),
        "alt_text": v.alt_text or "",
        "ordering": v.ordering,
        "is_primary": v.is_primary,
        "duration_sec": v.duration_sec,
        "barcode": v.barcode or "",
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
        "condition": product.condition,
        "gender_target": product.gender_target or "",
        "age_group": product.age_group or "",
        "is_pre_order": product.is_pre_order,
        "pre_order_date": product.pre_order_date,
        "sustainability_score": product.sustainability_score,
        "carbon_footprint_kg": product.carbon_footprint_kg,
        "ai_trend_score": product.ai_trend_score,
        "created_at": product.created_at,
    }


def _product_detail_out(product) -> dict:
    """Full product detail including gallery, variants, specs, FAQs."""
    card = _product_card_out(product)
    prefetched_cache = getattr(product, "_prefetched_objects_cache", {}) or {}
    cached_variants = getattr(product, "_prefetched_variants", None)
    prefetched_variants = (
        list(cached_variants)
        if cached_variants is not None
        else list(prefetched_cache.get("product_variants_gallery_media", []))
    )
    if not prefetched_variants:
        try:
            prefetched_variants = list(product.product_variants_gallery_media.all())
        except Exception:
            prefetched_variants = []
    active_variants = [
        variant
        for variant in prefetched_variants
        if not getattr(variant, "is_deleted", False)
    ]
    gallery_items = [variant for variant in active_variants if getattr(variant, "media", None)]

    try:
        fabric_obj = product.product_fabric
    except ObjectDoesNotExist:
        fabric_obj = None

    try:
        shipping_obj = product.product_custom_shipping_profile
    except ObjectDoesNotExist:
        shipping_obj = None

    fabric_data = None
    if fabric_obj:
        fabric_data = {
            "id": str(fabric_obj.pk),
            "fabric_type": fabric_obj.fabric_type,
            "care_instructions": fabric_obj.care_instructions,
            "is_organic": fabric_obj.is_organic,
            "is_vegan": fabric_obj.is_vegan,
            "country_of_origin": fabric_obj.country_of_origin or "",
        }

    shipping_data = None
    if shipping_obj:
        shipping_data = {
            "id": str(shipping_obj.pk),
            "weight_kg": shipping_obj.weight_kg,
            "length_cm": shipping_obj.length_cm,
            "width_cm": shipping_obj.width_cm,
            "height_cm": shipping_obj.height_cm,
            "is_fragile": shipping_obj.is_fragile,
            "requires_signature": shipping_obj.requires_signature,
            "restricted_countries": shipping_obj.restricted_countries or [],
            "free_shipping_threshold": shipping_obj.free_shipping_threshold,
            "processing_days": shipping_obj.processing_days,
        }

    guide_rows = []
    try:
        for row in product.product_measurement_guide.all():
            guide_rows.append({
                "id": str(row.pk),
                "size_label": row.size_label,
                "chest_cm": row.chest_cm or "",
                "waist_cm": row.waist_cm or "",
                "hip_cm": row.hip_cm or "",
                "shoulder_cm": row.shoulder_cm or "",
                "sleeve_cm": row.sleeve_cm or "",
                "length_cm": row.length_cm or "",
                "inseam_cm": row.inseam_cm or "",
                "foot_length_cm": row.foot_length_cm or "",
                "sort_order": row.sort_order,
            })
    except Exception:
        pass

    card.update(
        {
            "description": product.description or "",
            "shipping_amount": _money(product.shipping_amount),
            "cover_image_url": card.get("image_url"),
            "gallery": [_gallery_item_out(m) for m in gallery_items],
            "max_stock": getattr(product, "max_stock", None),
            "views": product.views,
            "orders_count": product.orders_count,
            "sub_category_name": (
                product.primary_sub_category.name
                if getattr(product, "primary_sub_category", None)
                else None
            ),
            "categories": [_category_out(c) for c in product.categories.all()],
            "sub_categories": [_category_out(c) for c in product.sub_categories.all()],
            "tags": [_tag_out(t) for t in product.tags.all()],
            "specifications": [],
            "faqs": [
                {"id": str(f.pk), "question": f.question, "answer": f.answer}
                for f in product.faqs.all()
            ],
            "variants": [_variant_out(v) for v in active_variants],
            "status": product.status,
            "vendor": _vendor_out(product.vendor),
            "vendor_id": str(product.vendor.pk) if product.vendor else None,
            "vendor_name": _vendor_out(product.vendor)["store_name"],
            "vendor_slug": _vendor_out(product.vendor)["slug"],
            "vendor_is_verified": _vendor_out(product.vendor)["is_verified"],
            "commission_rate": _money(product.commission_rate),
            "measurement_template_id": (
                str(
                    __import__("uuid").UUID(
                        bytes=__import__("hashlib").md5(
                            f"{product.vendor.pk}-{product.measurement_template}".encode("utf-8")
                        ).digest()
                    )
                )
                if product.measurement_template and product.vendor
                else None
            ),
            "weight_kg": product.weight_kg,
            "condition": product.condition,
            "is_pre_order": product.is_pre_order,
            "pre_order_date": product.pre_order_date,
            "meta_title": product.meta_title or "",
            "meta_description": product.meta_description or "",
            "age_group": product.age_group or "",
            "gender_target": product.gender_target or "",
            "fabric": fabric_data,
            "measurement_guide": guide_rows,
            "shipping_profile": shipping_data,
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
    sub_category: str | None = None,
    brand: str | None = None,
    vendor: str | None = None,
    in_stock: bool | None = None,
    featured: bool | None = None,
    hot_deal: bool | None = None,
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
        sub_category=sub_category,
        brand=brand,
        vendor=vendor,
        in_stock=in_stock,
        featured=featured,
        hot_deal=hot_deal,
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


# ── VENDOR — Sizes, Colors, Couriers ──────────────────────────────────────────

@router.get("/sizes/", response=dict, auth=None, summary="List available sizes")
async def list_sizes(request, page: int = 1, page_size: int = 100):
    # Static choices matching SIZE_CHOICES for ProductSizeAndMeasurementGuide
    choices = ["XS", "S", "M", "L", "XL", "XXL", "Custom"]
    import uuid
    import hashlib
    results = []
    for name in choices:
        ns_uuid = uuid.UUID(bytes=hashlib.md5(name.encode("utf-8")).digest())
        results.append({
            "id": str(ns_uuid),
            "name": name,
        })
    return {
        "count": len(results),
        "next": None,
        "previous": None,
        "results": results,
    }



@router.get("/couriers/", response=dict, auth=None, summary="List available couriers")
async def list_couriers(request, page: int = 1, page_size: int = 50, active: bool | None = None):
    from apps.product.models import DeliveryCourier
    qs = DeliveryCourier.objects.all().order_by("name")
    if active is not None:
        qs = qs.filter(active=active)

    def _courier_out(c):
        return {
            "id": str(c.pk),
            "name": c.name,
            "active": c.active,
            "base_fee": _money(c.base_fee),
            "estimated_days_min": c.estimated_days_min,
            "estimated_days_max": c.estimated_days_max,
            "logo_url": _url(c.logo),
        }

    return await _paginated(request, qs, _courier_out, page=page, page_size=page_size)


# ── VENDOR — Sessions ──────────────────────────────────────────────────

def _get_templates_sync(profile):
    from apps.product.models import ProductSizeAndMeasurementGuide
    rows = ProductSizeAndMeasurementGuide.objects.filter(
        vendor=profile,
        save_as_template=True,
    ).order_by("name", "sort_order")

    from collections import defaultdict
    templates_dict = defaultdict(list)
    for r in rows:
        templates_dict[r.name].append(r)

    results = []
    for name, t_rows in templates_dict.items():
        import uuid
        import hashlib
        h = hashlib.md5(f"{profile.pk}-{name}".encode("utf-8")).digest()
        t_uuid = uuid.UUID(bytes=h)

        rows_list = []
        for r in t_rows:
            rows_list.append({
                "id": str(r.pk),
                "size_id": str(r.pk),
                "size_label": r.size_label,
                "chest_cm": r.chest_cm or "",
                "waist_cm": r.waist_cm or "",
                "hip_cm": r.hip_cm or "",
                "length_cm": r.length_cm or "",
                "shoulder_cm": r.shoulder_cm or "",
                "sleeve_cm": r.sleeve_cm or "",
                "inseam_cm": r.inseam_cm or "",
                "foot_length_cm": r.foot_length_cm or "",
                "sort_order": r.sort_order,
            })
        results.append({
            "id": str(t_uuid),
            "vendor_id": str(profile.pk),
            "name": name,
            "description": "Measurement template rows",
            "template_rows": rows_list,
        })
    return results


@router.get("/vendor/measurement-templates/", response=list[VendorMeasurementTemplateOut], summary="List vendor's reusable measurement templates")
async def list_measurement_templates(request):
    from asgiref.sync import sync_to_async
    profile = await _require_vendor(request)
    return await sync_to_async(_get_templates_sync)(profile)


@router.post("/vendor/measurement-templates/", response=VendorMeasurementTemplateOut, summary="Create/update a reusable measurement template")
async def create_measurement_template(request, payload: VendorMeasurementTemplateIn):
    profile = await _require_vendor(request)
    from asgiref.sync import sync_to_async
    import django.db.transaction
    from apps.product.models import ProductSizeAndMeasurementGuide
    
    def _save_template():
        with django.db.transaction.atomic():
            # Delete existing template rows for this vendor & name
            ProductSizeAndMeasurementGuide.objects.filter(
                vendor=profile,
                save_as_template=True,
                name=payload.name,
            ).delete()
            
            db_desc = payload.description
            if db_desc not in [c[0] for c in ProductSizeAndMeasurementGuide.DESCRIPTION_CHOICES]:
                db_desc = "custom"
            
            created_rows = []
            for row in payload.template_rows:
                created = ProductSizeAndMeasurementGuide.objects.create(
                    vendor=profile,
                    name=payload.name,
                    description=db_desc,
                    size_label=row.size_label,
                    chest_cm=row.chest_cm,
                    waist_cm=row.waist_cm,
                    hip_cm=row.hip_cm,
                    length_cm=row.length_cm,
                    shoulder_cm=row.shoulder_cm,
                    sleeve_cm=row.sleeve_cm,
                    inseam_cm=row.inseam_cm,
                    foot_length_cm=row.foot_length_cm,
                    sort_order=row.sort_order,
                    save_as_template=True,
                )
                created_rows.append(created)
            
            # Deterministic UUID for the template
            import uuid
            import hashlib
            h = hashlib.md5(f"{profile.pk}-{payload.name}".encode("utf-8")).digest()
            t_uuid = uuid.UUID(bytes=h)
            
            rows_list = []
            for r in created_rows:
                rows_list.append({
                    "id": str(r.pk),
                    "size_id": str(r.pk),
                    "size_label": r.size_label,
                    "chest_cm": r.chest_cm or "",
                    "waist_cm": r.waist_cm or "",
                    "hip_cm": r.hip_cm or "",
                    "length_cm": r.length_cm or "",
                    "shoulder_cm": r.shoulder_cm or "",
                    "sleeve_cm": r.sleeve_cm or "",
                    "inseam_cm": r.inseam_cm or "",
                    "foot_length_cm": r.foot_length_cm or "",
                    "sort_order": r.sort_order,
                })
                
            return {
                "id": str(t_uuid),
                "vendor_id": str(profile.pk),
                "name": payload.name,
                "description": payload.description,
                "template_rows": rows_list,
            }
            
    return await sync_to_async(_save_template)()



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
        user = await _resolve_optional_bearer_user(request)
        vendor = None
        if user and is_vendor_role(getattr(user, "role", None)):
            try:
                vendor = user.vendor_profile
            except ObjectDoesNotExist:
                pass

        product = None
        if vendor:
            product = await aget_vendor_product(vendor.pk, slug)
        if not product:
            product = await aget_product_detail(slug)

        if not product:
            raise HttpError(404, "Product not found.")

        from apps.product.models.product import ProductStatus
        if product.status == ProductStatus.PUBLISHED:
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

    vendor = None
    if user and is_vendor_role(getattr(user, "role", None)):
        try:
            vendor = user.vendor_profile
        except ObjectDoesNotExist:
            pass

    try:
        product = None
        if vendor:
            product = await aget_vendor_product(vendor.pk, slug)

        if product:
            reviews, in_wishlist = await asyncio.gather(
                alist_reviews_for_product_slug(slug, limit=20),
                auser_has_wishlist_slug(user, slug),
            )
        else:
            product_dict = await aget_product_detail_bundle(
                slug=slug,
                user_id=user.pk if user else None,
                session_key=None,  # session key handling inside get_product_detail_bundle
            )
            product = product_dict.get("product")
            reviews = product_dict.get("reviews")
            in_wishlist = product_dict.get("in_wishlist")

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
        for m in product.product_variants_gallery_media.all()
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
