# apps/product/services/async_product_service.py
"""
Async compatibility services for legacy Ninja product mutation routes.

Canonical product writes must stay in DRF sync services with transaction.atomic().
These functions exist only so older async routes do not import thread adapters.
All database work uses native Django async ORM terminals.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db.models import Avg, Count, F

from apps.product.models import (
    Coupon,
    Product,
    ProductInventoryLog,
    ProductReview,
    ProductViewLog,
    ProductWishlist,
)


async def async_increment_product_views(product_id: Any) -> None:
    """Atomically increment the product denormalized view counter."""
    await Product.objects.filter(pk=product_id).aupdate(views=F("views") + 1)


async def async_create_review(
    *,
    user: Any,
    product: Product,
    rating: int,
    review_text: str,
    idempotency_key: UUID | None = None,
) -> ProductReview:
    """Create a review using native async ORM and refresh product aggregates."""
    exists = await ProductReview.objects.filter(product=product, user=user).aexists()
    if exists:
        raise ValueError("You have already reviewed this product.")

    review = await ProductReview.objects.acreate(
        product=product,
        user=user,
        rating=rating,
        review=review_text,
        idempotency_key=idempotency_key,
    )
    aggregate = await ProductReview.objects.filter(
        product=product,
        active=True,
    ).aaggregate(avg=Avg("rating"), total=Count("id"))
    await Product.objects.filter(pk=product.pk).aupdate(
        rating=round(aggregate["avg"] or 0, 1),
        review_count=aggregate["total"] or 0,
    )
    return review


async def async_create_review_for_slug(
    *,
    user: Any,
    slug: str,
    rating: int,
    review_text: str,
    idempotency_key: UUID | None = None,
) -> ProductReview:
    """Resolve a product slug, then create a review through the async service."""
    product = await Product.objects.only("id").aget(slug=slug, is_deleted=False)
    return await async_create_review(
        user=user,
        product=product,
        rating=rating,
        review_text=review_text,
        idempotency_key=idempotency_key,
    )


async def async_toggle_wishlist(
    *,
    user: Any | None = None,
    session_key: str | None = None,
    product: Product,
) -> dict:
    """Toggle a wishlist entry for an authenticated or anonymous owner."""
    if user is not None and getattr(user, "is_authenticated", False):
        if session_key:
            raise ValueError("Authenticated wishlist writes must not include session_key.")
        identity = {"user": user, "session_key": None}
    elif session_key:
        identity = {"user": None, "session_key": session_key}
    else:
        raise ValueError("Wishlist requires either user or session_key.")

    entry = await ProductWishlist.objects.filter(product=product, **identity).afirst()
    if entry:
        await ProductWishlist.objects.filter(pk=entry.pk).adelete()
        return {"added": False}

    await ProductWishlist.objects.acreate(product=product, **identity)
    return {"added": True}


async def async_toggle_wishlist_for_slug(
    *,
    user: Any | None = None,
    session_key: str | None = None,
    slug: str,
) -> dict:
    """Resolve a product slug, then toggle wishlist ownership through service logic."""
    product = await Product.objects.only("id").aget(slug=slug, is_deleted=False)
    return await async_toggle_wishlist(
        user=user,
        session_key=session_key,
        product=product,
    )


async def async_adjust_inventory(
    *,
    product: Product,
    quantity_delta: int,
    reason: str,
    actor: Any = None,
    note: str = "",
    reference_id: str = "",
) -> ProductInventoryLog:
    """
    Adjust inventory without thread adapters.

    This is a compatibility path for legacy Ninja writes. Canonical contested
    inventory writes should call the sync ProductService under transaction.atomic().
    """
    current = await Product.objects.only("id", "stock_qty", "max_stock").aget(pk=product.pk)
    before = current.stock_qty
    after = max(0, before + quantity_delta)
    if current.max_stock is not None and current.max_stock > 0:
        after = min(after, current.max_stock)

    await Product.objects.filter(pk=product.pk).aupdate(
        stock_qty=after,
        in_stock=after > 0,
    )
    return await ProductInventoryLog.objects.acreate(
        product=product,
        actor=actor,
        quantity_delta=quantity_delta,
        quantity_before=before,
        quantity_after=after,
        reason=reason,
        reference_id=reference_id,
        note=note,
    )


async def async_validate_and_apply_coupon(
    *,
    code: str,
    user: Any,
    order_subtotal: Decimal,
) -> dict:
    """Validate a coupon with native async ORM; no usage mutation is performed."""
    coupon = await Coupon.objects.filter(code__iexact=code, is_deleted=False).afirst()
    if not coupon:
        raise ValueError("Coupon not found.")
    if not coupon.is_valid():
        raise ValueError("Coupon is expired or has reached its usage limit.")
    if order_subtotal < coupon.minimum_order:
        raise ValueError(
            f"Minimum order amount is {coupon.minimum_order} to use this coupon."
        )

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


async def async_record_product_view(
    *,
    slug: str,
    user: Any | None = None,
    session_key: str | None = None,
    referrer_url: str | None = None,
    device_type: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
) -> dict:
    """Write a best-effort product view log without leaking ORM into API views."""
    product = await Product.objects.only("pk").filter(
        slug=slug, is_deleted=False
    ).afirst()
    if not product:
        return {"logged": False, "reason": "product_not_found"}

    valid_devices = {"desktop", "mobile", "tablet", "unknown"}
    clean_device = device_type if device_type in valid_devices else "unknown"

    await ProductViewLog.objects.acreate(
        product=product,
        user=user if user else None,
        session_key=(session_key or "")[:40],
        referrer_url=(referrer_url or "")[:500],
        device_type=clean_device,
        utm_source=(utm_source or "")[:100],
        utm_medium=(utm_medium or "")[:100],
        utm_campaign=(utm_campaign or "")[:100],
    )
    await async_increment_product_views(product.pk)
    return {"logged": True}
