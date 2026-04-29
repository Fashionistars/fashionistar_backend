"""Cart Django-Ninja async read router."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from ninja import Router
from ninja.errors import HttpError

from apps.cart.schemas import CartOut
from apps.cart.selectors import CartSelector
from apps.common.roles import is_client_role

router = Router(tags=["Cart — Async Reads"])


def _money(value) -> str:
    """Return monetary values as stable decimal strings for Zod contracts."""

    if value is None:
        return "0.00"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def _media_url(value) -> str | None:
    """Return a Cloudinary-backed secure URL when one exists."""

    if not value:
        return None
    try:
        return str(value.url)
    except (AttributeError, ValueError):
        return str(value) if value else None


def _require_client_profile(request):
    """Return the hydrated client profile from request.auth."""

    user = request.auth
    if user is None or not is_client_role(getattr(user, "role", None)):
        raise HttpError(403, "Client access is required for this endpoint.")

    try:
        profile = user.client_profile
    except (AttributeError, ObjectDoesNotExist):
        profile = None

    if profile is None:
        raise HttpError(403, "Client profile setup is required for this endpoint.")
    return profile


def _product_out(product) -> dict:
    """Serialize the compact product reference shown in cart rows."""

    vendor = getattr(product, "vendor", None)
    return {
        "id": str(product.pk),
        "slug": product.slug,
        "title": product.title,
        "sku": product.sku,
        "cover_image_url": _media_url(getattr(product, "image", None)),
        "requires_measurement": product.requires_measurement,
        "vendor_name": getattr(vendor, "store_name", "") or "Fashionistar",
    }


def _item_out(item) -> dict:
    """Serialize one active cart line with variant labels."""

    variant = getattr(item, "variant", None)
    size = getattr(variant, "size", None) if variant else None
    color = getattr(variant, "color", None) if variant else None
    currency = getattr(item.product, "currency", "NGN") or "NGN"
    return {
        "id": str(item.pk),
        "product": _product_out(item.product),
        "variant_id": str(variant.pk) if variant else None,
        "size_label": getattr(size, "name", None),
        "color_label": getattr(color, "name", None),
        "quantity": item.quantity,
        "unit_price": _money(item.unit_price),
        "line_total": _money(item.line_total),
        "currency": currency,
    }


def _empty_cart_out() -> dict:
    """Return a read-only empty cart without creating a database row."""

    return {
        "id": None,
        "items": [],
        "item_count": 0,
        "subtotal": "0.00",
        "currency": "NGN",
        "expires_at": None,
    }


@router.get("/", response=CartOut)
async def get_current_cart(request):
    """Return the authenticated client's cart without mutating state."""

    _require_client_profile(request)
    cart = await CartSelector.aget_for_user_or_none(request.auth)
    if cart is None:
        return _empty_cart_out()

    # Cart reads are capped to 25 active rows to keep badge/nav reads fast.
    items = [
        item for item in cart.items.all()
        if not getattr(item, "is_saved_for_later", False)
    ][:25]
    currency = items[0].product.currency if items else "NGN"
    subtotal = sum((item.line_total for item in items), Decimal("0"))
    return {
        "id": str(cart.pk),
        "items": [_item_out(item) for item in items],
        "item_count": sum(item.quantity for item in items),
        "subtotal": _money(subtotal),
        "currency": currency,
        "expires_at": None,
    }
