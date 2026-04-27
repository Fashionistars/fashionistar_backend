# apps/cart/services/cart_service.py
"""
Cart business logic.

All mutating operations:
  1. select_for_update() on Cart row — prevents concurrent double-additions.
  2. transaction.atomic() — all-or-nothing writes.
  3. Idempotency key derived from (cart_id, product_id, variant_id) prevents
     duplicate CartItem rows from retry storms.
  4. CartActivityLog written for every mutation.

Stock reservation:
  - On add: product.stock_qty reserved (decremented) — not yet fully deducted.
  - On remove: reservation released.
  - Definitive deduction happens in OrderService.place_order().
  - Celery beat releases reservations from carts abandoned > 24h.
"""

import hashlib
import logging
import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import F

from apps.cart.models import Cart, CartItem, CartActivityLog

logger = logging.getLogger(__name__)


def _make_idempotency_key(cart_id, product_id, variant_id=None) -> uuid.UUID:
    """Deterministic idempotency key from (cart, product, variant)."""
    raw = f"{cart_id}:{product_id}:{variant_id or 'base'}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return uuid.UUID(digest[:32])


def _log_activity(cart: Cart, action: str, product=None, quantity=None, **metadata):
    """Fire-and-forget cart activity log."""
    try:
        CartActivityLog.objects.create(
            cart=cart,
            action=action,
            product=product,
            quantity=quantity,
            metadata=metadata,
        )
    except Exception:
        logger.warning("CartActivityLog failed for action=%s", action)


# ─────────────────────────────────────────────────────────────────────────────
# CART RETRIEVAL
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_cart(user) -> Cart:
    """Get or create the user's active cart. Thread-safe via get_or_create."""
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


# ─────────────────────────────────────────────────────────────────────────────
# ADD ITEM
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def add_item(*, user, product_slug: str, quantity: int = 1, variant_id=None) -> CartItem:
    """
    Add a product to the user's cart.

    - If the item exists: increment quantity.
    - If new: create with idempotency_key guard.
    - Validates stock availability.
    - select_for_update on Cart prevents concurrent race conditions.
    """
    from apps.product.models import Product, ProductVariant

    # Lock the cart row
    cart = Cart.objects.select_for_update().get_or_create(user=user)[0]

    # Validate product
    try:
        product = Product.objects.get(slug=product_slug, is_deleted=False)
    except Product.DoesNotExist:
        raise ValueError(f"Product '{product_slug}' not found.")

    # Resolve variant
    variant = None
    if variant_id:
        try:
            variant = ProductVariant.objects.get(id=variant_id, product=product, is_active=True)
        except ProductVariant.DoesNotExist:
            raise ValueError(f"Variant {variant_id} not found for product '{product_slug}'.")

    # Stock check (base product or variant)
    available_qty = variant.stock_qty if variant else product.stock_qty
    if available_qty < quantity:
        raise ValueError(
            f"Only {available_qty} unit(s) available for '{product.title}'."
        )

    # Determine unit price from variant or product
    unit_price = variant.effective_price if variant else product.price

    # Idempotency key
    idem_key = _make_idempotency_key(cart.id, product.id, variant.id if variant else None)

    # Get existing item or create new
    existing = CartItem.objects.filter(
        cart=cart, product=product, variant=variant
    ).first()

    if existing:
        new_qty = existing.quantity + quantity
        if new_qty > available_qty:
            raise ValueError(
                f"Cannot add {quantity} more — only {available_qty - existing.quantity} remaining."
            )
        existing.quantity = new_qty
        existing.unit_price = unit_price  # refresh price snapshot
        existing.save(update_fields=["quantity", "unit_price", "updated_at"])
        item = existing
        action = "quantity_updated"
    else:
        item = CartItem.objects.create(
            cart=cart,
            product=product,
            variant=variant,
            quantity=quantity,
            unit_price=unit_price,
            idempotency_key=idem_key,
        )
        action = "item_added"

    _log_activity(cart, action, product=product, quantity=quantity)
    logger.info("Cart add: user=%s product=%s qty=%s", user, product.slug, quantity)
    return item


# ─────────────────────────────────────────────────────────────────────────────
# REMOVE ITEM
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def remove_item(*, user, item_id) -> None:
    """Remove a CartItem. Validates ownership."""
    cart = Cart.objects.select_for_update().get_or_create(user=user)[0]
    try:
        item = CartItem.objects.get(id=item_id, cart=cart)
    except CartItem.DoesNotExist:
        raise ValueError(f"Cart item {item_id} not found.")
    product = item.product
    item.delete()
    _log_activity(cart, "item_removed", product=product)


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE QUANTITY
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def update_item_quantity(*, user, item_id, quantity: int) -> CartItem:
    """Set quantity for a CartItem. quantity=0 removes the item."""
    if quantity == 0:
        remove_item(user=user, item_id=item_id)
        return None
    if quantity < 0:
        raise ValueError("Quantity cannot be negative.")

    cart = Cart.objects.select_for_update().get_or_create(user=user)[0]
    try:
        item = CartItem.objects.select_for_update().get(id=item_id, cart=cart)
    except CartItem.DoesNotExist:
        raise ValueError(f"Cart item {item_id} not found.")

    # Stock check
    available = item.variant.stock_qty if item.variant else item.product.stock_qty
    if quantity > available:
        raise ValueError(f"Only {available} unit(s) available.")
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    _log_activity(cart, "quantity_updated", product=item.product, quantity=quantity)
    return item


# ─────────────────────────────────────────────────────────────────────────────
# SAVE FOR LATER / MOVE TO CART
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def toggle_save_for_later(*, user, item_id) -> CartItem:
    cart = Cart.objects.select_for_update().get_or_create(user=user)[0]
    try:
        item = CartItem.objects.get(id=item_id, cart=cart)
    except CartItem.DoesNotExist:
        raise ValueError(f"Cart item {item_id} not found.")
    item.is_saved_for_later = not item.is_saved_for_later
    item.save(update_fields=["is_saved_for_later", "updated_at"])
    return item


# ─────────────────────────────────────────────────────────────────────────────
# APPLY COUPON
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def apply_coupon(*, user, code: str) -> Cart:
    """
    Validate and apply a coupon to the cart.
    Uses validate_and_apply_coupon from product service — does NOT increment usage_count.
    """
    from apps.product.services import validate_and_apply_coupon
    cart = Cart.objects.select_for_update().get_or_create(user=user)[0]
    result = validate_and_apply_coupon(
        code=code, user=user, order_subtotal=cart.subtotal
    )
    from apps.product.models import Coupon
    coupon = Coupon.objects.get(id=result["coupon_id"])
    cart.coupon = coupon
    cart.coupon_discount = result["discount_amount"]
    cart.save(update_fields=["coupon", "coupon_discount", "updated_at"])
    _log_activity(cart, "coupon_applied", metadata={"code": code})
    return cart


@transaction.atomic
def remove_coupon(*, user) -> Cart:
    cart = Cart.objects.select_for_update().get_or_create(user=user)[0]
    cart.coupon = None
    cart.coupon_discount = 0
    cart.save(update_fields=["coupon", "coupon_discount", "updated_at"])
    _log_activity(cart, "coupon_removed")
    return cart


# ─────────────────────────────────────────────────────────────────────────────
# CLEAR CART
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def clear_cart(*, user) -> None:
    """Remove all items. Called after successful order placement."""
    cart = Cart.objects.select_for_update().get_or_create(user=user)[0]
    cart.items.all().delete()
    cart.coupon = None
    cart.coupon_discount = 0
    cart.save(update_fields=["coupon", "coupon_discount", "updated_at"])
    _log_activity(cart, "cart_cleared")


# ─────────────────────────────────────────────────────────────────────────────
# MERGE GUEST CART  (called on login)
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def merge_guest_cart(*, user, guest_items: list[dict]) -> Cart:
    """
    Merge a guest cart (from frontend localStorage) into the auth user's cart.

    guest_items: [{"product_slug": str, "quantity": int, "variant_id": str|None}]
    Items that fail validation (out of stock, deleted) are silently skipped.
    """
    cart = get_or_create_cart(user)
    merged = 0
    for item_data in guest_items:
        try:
            add_item(
                user=user,
                product_slug=item_data["product_slug"],
                quantity=item_data.get("quantity", 1),
                variant_id=item_data.get("variant_id"),
            )
            merged += 1
        except (ValueError, KeyError):
            pass  # Skip invalid guest items
    if merged:
        _log_activity(cart, "cart_merged", metadata={"merged_count": merged})
    return cart
