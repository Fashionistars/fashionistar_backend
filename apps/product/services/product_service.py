# apps/product/services/product_service.py
"""
Business logic for the Product domain.

Rules:
  - Services call selectors for reads, ORM for writes.
  - All writes use transaction.atomic().
  - Audit events emitted for all mutations.
  - Never raise Http404 — raise ValueError / PermissionError for views to handle.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Avg

from apps.product.models import (
    Product,
    ProductGalleryMedia,
    ProductInventoryLog,
    ProductReview,
    ProductWishlist,
    ProductStatus,
    Coupon,
)
from apps.product.selectors import (
    get_vendor_product_or_404,
    get_user_review_for_product,
    is_in_wishlist,
)

logger = logging.getLogger(__name__)


def _emit_audit(action: str, product: Product, actor=None, **metadata):
    """Fire-and-forget audit event. Never blocks the caller."""
    try:
        from apps.audit_logs.services.audit import AuditService
        from apps.audit_logs.models import EventType, EventCategory, SeverityLevel

        type_map = {
            "product.created": (EventType.RECORD_CREATED, EventCategory.BUSINESS, SeverityLevel.INFO),
            "product.updated": (EventType.RECORD_UPDATED, EventCategory.BUSINESS, SeverityLevel.INFO),
            "product.published": (EventType.RECORD_UPDATED, EventCategory.BUSINESS, SeverityLevel.INFO),
            "product.archived": (EventType.RECORD_DELETED, EventCategory.BUSINESS, SeverityLevel.WARNING),
            "product.media.attached": (EventType.RECORD_UPDATED, EventCategory.BUSINESS, SeverityLevel.INFO),
            "product.media.removed": (EventType.RECORD_DELETED, EventCategory.BUSINESS, SeverityLevel.WARNING),
            "product.review.created": (EventType.RECORD_CREATED, EventCategory.BUSINESS, SeverityLevel.INFO),
            "product.inventory.adjusted": (EventType.RECORD_UPDATED, EventCategory.BUSINESS, SeverityLevel.INFO),
        }
        event_type, category, severity = type_map.get(
            action,
            (EventType.RECORD_UPDATED, EventCategory.BUSINESS, SeverityLevel.INFO),
        )
        AuditService.log(
            event_type=event_type,
            event_category=category,
            severity=severity,
            action=action,
            actor=actor,
            resource_type="Product",
            resource_id=str(product.id),
            metadata={"product_slug": product.slug, **metadata},
            is_compliance=False,
        )
    except Exception:
        logger.warning("Audit event skipped for action=%s product=%s", action, getattr(product, "id", "?"))


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT CRUD
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_product(*, vendor, validated_data: dict) -> Product:
    """Create a new product for a vendor. Status starts as DRAFT."""
    sizes = validated_data.pop("sizes", [])
    colors = validated_data.pop("colors", [])
    tags = validated_data.pop("tags", [])
    product = Product.objects.create(
        vendor=vendor,
        status=ProductStatus.DRAFT,
        **validated_data,
    )
    if sizes:
        product.sizes.set(sizes)
    if colors:
        product.colors.set(colors)
    if tags:
        product.tags.set(tags)
    _emit_audit("product.created", product, actor=vendor.user if hasattr(vendor, "user") else None)
    logger.info("Product created: %s by vendor %s", product.slug, vendor)
    return product


@transaction.atomic
def update_product(*, product: Product, validated_data: dict, actor=None) -> Product:
    """Update product fields. Vendor-owned products only."""
    sizes = validated_data.pop("sizes", None)
    colors = validated_data.pop("colors", None)
    tags = validated_data.pop("tags", None)
    for attr, value in validated_data.items():
        setattr(product, attr, value)
    product.save()
    if sizes is not None:
        product.sizes.set(sizes)
    if colors is not None:
        product.colors.set(colors)
    if tags is not None:
        product.tags.set(tags)
    _emit_audit("product.updated", product, actor=actor)
    return product


@transaction.atomic
def publish_product(*, product: Product, actor=None) -> Product:
    """Submit product for review → status: pending."""
    if product.status not in (ProductStatus.DRAFT, ProductStatus.REJECTED):
        raise ValueError(f"Cannot publish product with status '{product.status}'.")
    product.status = ProductStatus.PENDING
    product.save(update_fields=["status", "updated_at"])
    _emit_audit("product.published", product, actor=actor)
    return product


@transaction.atomic
def approve_product(*, product: Product, actor=None) -> Product:
    """Admin/moderator approves product → status: published."""
    product.status = ProductStatus.PUBLISHED
    product.save(update_fields=["status", "updated_at"])
    _emit_audit("product.published", product, actor=actor, new_status="published")
    return product


@transaction.atomic
def archive_product(*, product: Product, actor=None) -> Product:
    """Soft-archive — removes from storefront but keeps record."""
    product.status = ProductStatus.ARCHIVED
    product.save(update_fields=["status", "updated_at"])
    _emit_audit("product.archived", product, actor=actor)
    return product


# ─────────────────────────────────────────────────────────────────────────────
# GALLERY / MEDIA
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def attach_gallery_media(*, product: Product, media_file, media_type: str = "image", alt_text: str = "", actor=None) -> ProductGalleryMedia:
    ordering = product.gallery.count() + 1
    gallery_item = ProductGalleryMedia.objects.create(
        product=product,
        media=media_file,
        media_type=media_type,
        alt_text=alt_text,
        ordering=ordering,
    )
    _emit_audit("product.media.attached", product, actor=actor, media_id=str(gallery_item.id))
    return gallery_item


@transaction.atomic
def remove_gallery_media(*, product: Product, gallery_id, actor=None):
    try:
        item = ProductGalleryMedia.objects.get(id=gallery_id, product=product)
    except ProductGalleryMedia.DoesNotExist:
        raise ValueError(f"Gallery media {gallery_id} not found for product {product.slug}.")
    item.soft_delete()
    _emit_audit("product.media.removed", product, actor=actor, media_id=str(gallery_id))


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def adjust_inventory(
    *,
    product: Product,
    quantity_delta: int,
    reason: str,
    actor=None,
    variant=None,
    reference_id: str = "",
    note: str = "",
) -> ProductInventoryLog:
    """
    Atomic stock adjustment. Prevents negative stock.
    """
    # Lock the product row for update
    product = Product.objects.select_for_update().get(pk=product.pk)
    before = product.stock_qty
    after = max(0, before + quantity_delta)
    product.stock_qty = after
    product.in_stock = after > 0
    product.save(update_fields=["stock_qty", "in_stock", "updated_at"])
    log = ProductInventoryLog.objects.create(
        product=product,
        variant=variant,
        actor=actor,
        quantity_delta=quantity_delta,
        quantity_before=before,
        quantity_after=after,
        reason=reason,
        reference_id=reference_id,
        note=note,
    )
    _emit_audit(
        "product.inventory.adjusted", product, actor=actor,
        delta=quantity_delta, before=before, after=after, reason=reason,
    )
    return log


# ─────────────────────────────────────────────────────────────────────────────
# REVIEWS
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_review(*, user, product: Product, rating: int, review_text: str) -> ProductReview:
    existing = get_user_review_for_product(user.id, product.id)
    if existing:
        raise ValueError("You have already reviewed this product.")
    obj = ProductReview.objects.create(
        product=product,
        user=user,
        rating=rating,
        review=review_text,
    )
    # Update product aggregate rating
    agg = ProductReview.objects.filter(product=product, active=True).aggregate(avg=Avg("rating"))
    count = ProductReview.objects.filter(product=product, active=True).count()
    Product.objects.filter(pk=product.pk).update(
        rating=round(agg["avg"] or 0, 1),
        review_count=count,
    )
    _emit_audit("product.review.created", product, actor=user, rating=rating)
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# WISHLIST
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def toggle_wishlist(*, user, product: Product) -> dict:
    """Toggle product in user wishlist. Returns {added: bool}."""
    if is_in_wishlist(user.id, product.id):
        ProductWishlist.objects.filter(user=user, product=product).delete()
        return {"added": False}
    else:
        ProductWishlist.objects.create(user=user, product=product)
        return {"added": True}


# ─────────────────────────────────────────────────────────────────────────────
# COUPON
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def validate_and_apply_coupon(*, code: str, user, order_subtotal: Decimal) -> dict:
    """
    Validate coupon and return discount amount.
    Does NOT increment usage_count — that happens at checkout submit.
    """
    from apps.product.selectors import get_coupon_by_code
    coupon = get_coupon_by_code(code)
    if not coupon:
        raise ValueError("Coupon not found.")
    if not coupon.is_valid():
        raise ValueError("Coupon is expired or has reached its usage limit.")
    if order_subtotal < coupon.minimum_order:
        raise ValueError(f"Minimum order amount is {coupon.minimum_order} to use this coupon.")
    if coupon.discount_type == "percentage":
        discount = (coupon.discount_value / 100) * order_subtotal
        if coupon.maximum_discount:
            discount = min(discount, coupon.maximum_discount)
    else:
        discount = min(coupon.discount_value, order_subtotal)
    return {
        "coupon_id": str(coupon.id),
        "code": coupon.code,
        "discount_type": coupon.discount_type,
        "discount_amount": discount,
    }
