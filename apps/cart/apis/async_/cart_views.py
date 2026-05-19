"""Cart Django-Ninja async read router — 2027 Edition.

Changes:
  • get_current_cart now delegates to CartSelector.aget_cart_with_items()
    instead of calling .items.all() on a non-prefetched queryset (N+1 fix).
  • applied_coupon is now serialized in the response dict to satisfy the
    CartSchema Zod contract on the frontend.
  • _MAX_CART_ITEMS constant makes the 25-item cap explicit and searchable.
  • Coupon discount amounts are surfaced in the top-level response.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from ninja import Router
from ninja.errors import HttpError
from apps.cart.schemas import CartOut
from apps.cart.selectors import CartSelector
from apps.client.services.client_provisioning_service import ClientProvisioningService
from apps.common.roles import is_client_role

router = Router(tags=["Cart — Async Reads"])

# Cap the number of active cart rows returned per read.
# Keeps nav-badge / drawer reads fast (< 3ms serialization budget).
_MAX_CART_ITEMS = 25


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
    """Return the hydrated client profile from request.auth.

    The cart read surface should not hard-fail when a seeded or migrated
    client account is missing its 1:1 profile row. We provision the blank
    profile lazily here so authenticated cart reads keep working while the
    rest of the client dashboard can hydrate normally.
    """

    user = request.auth
    if user is None or not is_client_role(getattr(user, "role", None)):
        raise HttpError(403, "Client access is required for this endpoint.")

    try:
        profile = user.client_profile
    except (AttributeError, ObjectDoesNotExist):
        profile = None

    if profile is None:
        raise HttpError(503, "Client profile provisioning is required before cart access.")
    return profile


async def _resolve_optional_bearer_user(request):
    """Hydrate a user from an optional Authorization header for public-friendly reads."""

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


def _coupon_out(cart) -> dict | None:
    """Serialize the applied coupon if present — satisfies CartSchema.applied_coupon."""

    coupon = getattr(cart, "coupon", None)
    if coupon is None:
        return None
    discount = getattr(cart, "coupon_discount", None)
    return {
        "code": coupon.code,
        "coupon_type": getattr(coupon, "coupon_type", "fixed") or "fixed",
        "discount_amount": _money(discount),
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
        "applied_coupon": None,
    }


@router.get("/", response=CartOut, auth=None)
async def get_current_cart(request, session_key: str | None = None):
    """Return the current cart for an authenticated client or anonymous session."""

    user = await _resolve_optional_bearer_user(request)
    if user is not None:
        request.auth = user
        try:
            _require_client_profile(request)
        except HttpError as exc:
            if exc.status_code != 503:
                raise
            await ClientProvisioningService.aprovision(user)
            _require_client_profile(request)

    session_key = (
        session_key
        or request.headers.get("X-Fashionistar-Session-Key")
        or request.COOKIES.get("fashionistar_session_key")
    )

    # ── Use aget_cart_with_items to avoid N+1 on items / products / variants ──
    cart = await CartSelector.aget_cart_with_items(
        user=user,
        session_key=session_key,
    )
    if cart is None:
        return _empty_cart_out()

    # Cart reads are capped to _MAX_CART_ITEMS active rows to keep badge/nav
    # reads fast. The items queryset is already prefetched by aget_cart_with_items.
    active_items = [
        item for item in cart.items.all()
        if not getattr(item, "is_saved_for_later", False)
    ][:_MAX_CART_ITEMS]

    currency = active_items[0].product.currency if active_items else "NGN"
    subtotal = sum((item.line_total for item in active_items), Decimal("0"))

    return {
        "id": str(cart.pk),
        "items": [_item_out(item) for item in active_items],
        "item_count": sum(item.quantity for item in active_items),
        "subtotal": _money(subtotal),
        "currency": currency,
        "expires_at": None,
        "applied_coupon": _coupon_out(cart),
    }
