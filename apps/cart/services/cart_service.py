# apps/cart/services/cart_service.py
"""
Cart business logic.

All mutating operations:
  1. select_for_update() on Cart row — prevents concurrent double-additions.
  2. transaction.atomic() — all-or-nothing writes.
  3. Idempotency key derived from (cart_id, product_id, variant_id) prevents
     duplicate CartItem rows from retry storms.
  4. CartActivityLog written for every mutation.
  5. Audit events emitted for all mutations via cart_audit domain helper.

Stock reservation:
  - On add: product.stock_qty reserved (decremented) — not yet fully deducted.
  - On remove: reservation released.
  - Definitive deduction happens in OrderService.place_order().
  - Celery beat releases reservations from carts abandoned > 24h.

Audit:
  All mutations fire audit events via
  ``apps.audit_logs.services.cart.cart_audit``.
  Imports are deferred inside function bodies to prevent circular imports
  during Django startup / makemigrations.
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


def _identity_kwargs(*, user=None, session_key: str | None = None) -> dict:
    """
    Return the single cart owner lookup used by all cart mutations.

    Args:
        user: Authenticated UnifiedUser, if present.
        session_key: Frontend-generated anonymous session key.

    Raises:
        ValueError: If neither or both owner identifiers are provided.
    """
    if user is not None and getattr(user, "is_authenticated", False):
        if session_key:
            raise ValueError("Authenticated cart writes must not include session_key.")
        return {"user": user}
    if session_key:
        return {"session_key": session_key, "user": None}
    raise ValueError("Cart requires either an authenticated user or session_key.")


def _locked_cart(*, user=None, session_key: str | None = None) -> Cart:
    """Return the cart row locked for a user or anonymous session."""
    identity = _identity_kwargs(user=user, session_key=session_key)
    return Cart.objects.select_for_update().get_or_create(**identity)[0]


# ─────────────────────────────────────────────────────────────────────────────
# CART RETRIEVAL
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_cart(user=None, *, session_key: str | None = None) -> Cart:
    """Get or create the active cart for a user or anonymous session."""
    identity = _identity_kwargs(user=user, session_key=session_key)
    cart, _ = Cart.objects.get_or_create(**identity)
    return cart


# ─────────────────────────────────────────────────────────────────────────────
# ADD ITEM
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def add_item(
    *,
    user=None,
    session_key: str | None = None,
    product_slug: str,
    quantity: int = 1,
    variant_id=None,
    request=None,
) -> CartItem:
    """
    Add a product to the user's cart.

    - If the item exists: increment quantity.
    - If new: create with idempotency_key guard.
    - Validates stock availability.
    - select_for_update on Cart prevents concurrent race conditions.
    """
    from apps.product.models import Product, ProductVariant

    # Lock the cart row
    cart = _locked_cart(user=user, session_key=session_key)

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
    logger.info(
        "Cart add: owner=%s product=%s qty=%s",
        cart.user_id or f"anon:{cart.session_key}",
        product.slug,
        quantity,
    )
    # ── Audit event ──────────────────────────────────────────────────────────
    try:
        from apps.audit_logs.services.cart import cart_audit
        cart_audit.log_cart_item_added(
            actor=user,
            cart_id=str(cart.id),
            product_id=str(product.id),
            quantity=quantity,
            request=request,
        )
    except Exception:
        logger.warning("cart_audit.log_cart_item_added failed silently", exc_info=True)
    return item


# ─────────────────────────────────────────────────────────────────────────────
# REMOVE ITEM
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def remove_item(*, user=None, session_key: str | None = None, item_id, request=None) -> None:
    """Remove a CartItem. Validates ownership."""
    cart = _locked_cart(user=user, session_key=session_key)
    try:
        item = CartItem.objects.get(id=item_id, cart=cart)
    except CartItem.DoesNotExist:
        raise ValueError(f"Cart item {item_id} not found.")
    product = item.product
    item.delete()
    _log_activity(cart, "item_removed", product=product)
    # ── Audit event ──────────────────────────────────────────────────────────
    try:
        from apps.audit_logs.services.cart import cart_audit
        cart_audit.log_cart_item_removed(
            actor=user,
            cart_id=str(cart.id),
            product_id=str(product.id),
            request=request,
        )
    except Exception:
        logger.warning("cart_audit.log_cart_item_removed failed silently", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE QUANTITY
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def update_item_quantity(
    *,
    user=None,
    session_key: str | None = None,
    item_id,
    quantity: int,
    request=None,
) -> CartItem:
    """Set quantity for a CartItem. quantity=0 removes the item."""
    if quantity == 0:
        remove_item(user=user, session_key=session_key, item_id=item_id, request=request)
        return None
    if quantity < 0:
        raise ValueError("Quantity cannot be negative.")

    cart = _locked_cart(user=user, session_key=session_key)
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
def toggle_save_for_later(*, user=None, session_key: str | None = None, item_id) -> CartItem:
    cart = _locked_cart(user=user, session_key=session_key)
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
def apply_coupon(*, user=None, session_key: str | None = None, code: str, request=None) -> Cart:
    """
    Validate and apply a coupon to the cart.
    Uses validate_and_apply_coupon from product service — does NOT increment usage_count.
    """
    from apps.product.services import validate_and_apply_coupon
    cart = _locked_cart(user=user, session_key=session_key)
    result = validate_and_apply_coupon(
        code=code, user=user, order_subtotal=cart.subtotal, request=request
    )
    from apps.product.models import Coupon
    coupon = Coupon.objects.get(id=result["coupon_id"])
    cart.coupon = coupon
    cart.coupon_discount = result["discount_amount"]
    cart.save(update_fields=["coupon", "coupon_discount", "updated_at"])
    _log_activity(cart, "coupon_applied", metadata={"code": code})
    # ── Audit event ──────────────────────────────────────────────────────────
    try:
        from apps.audit_logs.services.cart import cart_audit
        cart_audit.log_coupon_applied(
            actor=user,
            cart_id=str(cart.id),
            coupon_code=code,
            discount=str(result["discount_amount"]),
            request=request,
        )
    except Exception:
        logger.warning("cart_audit.log_coupon_applied failed silently", exc_info=True)
    return cart


@transaction.atomic
def remove_coupon(*, user=None, session_key: str | None = None) -> Cart:
    cart = _locked_cart(user=user, session_key=session_key)
    cart.coupon = None
    cart.coupon_discount = 0
    cart.save(update_fields=["coupon", "coupon_discount", "updated_at"])
    _log_activity(cart, "coupon_removed")
    return cart


# ─────────────────────────────────────────────────────────────────────────────
# CLEAR CART
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def clear_cart(*, user=None, session_key: str | None = None, request=None) -> None:
    """Remove all items. Called after successful order placement."""
    cart = _locked_cart(user=user, session_key=session_key)
    cart.items.all().hard_delete()
    cart.coupon = None
    cart.coupon_discount = 0
    cart.save(update_fields=["coupon", "coupon_discount", "updated_at"])
    _log_activity(cart, "cart_cleared")
    # ── Audit event (fire after commit — inside @transaction.atomic) ──────────
    try:
        from apps.audit_logs.services.cart import cart_audit
        transaction.on_commit(
            lambda: cart_audit.log_cart_cleared(
                actor=user,
                cart_id=str(cart.id),
                request=request,
            )
        )
    except Exception:
        logger.warning("cart_audit.cart_cleared failed silently", exc_info=True)


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


# ─────────────────────────────────────────────────────────────────────────────
# ANONYMOUS SESSION CART MERGE  (called on login — DB-backed session cart)
# ─────────────────────────────────────────────────────────────────────────────

def merge_anonymous_cart_session(*, user, session_key: str) -> Cart:
    """
    Promote a database-backed anonymous cart into the authenticated user cart.

    ── SERVICE-LAYER RBAC GUARD (Wave B3 — Fix 5) ──────────────────────────────
    CART MERGE — CLIENT-ONLY SERVICE GUARD

    Non-client users must NEVER have anonymous cart state merged into their
    account. This guard mirrors the wishlist service pattern and protects
    against callers that bypass the view-layer RBAC (Celery tasks, management
    commands, direct Django shell calls, webhook handlers).

    The guard is SILENT — it discards the session cart for non-client users
    without raising an exception. This prevents cart state pollution on
    vendor/admin accounts while remaining invisible to the caller.

    Role enforcement layers:
    1. Edge layer:    proxy.ts COMMERCE_ONLY_PREFIXES
    2. Route layer:   CommerceRouteGuard
    3. Mutation layer: ensureCommerceAccess()
    4. View layer:    DRF permission class
    5. Service layer: THIS GUARD ← symmetric with wishlist service
    ─────────────────────────────────────────────────────────────────────────────

    Args:
        user: Authenticated user receiving the cart rows.
        session_key: Stable frontend-generated anonymous commerce key.

    Returns:
        The authenticated user's cart after the merge is complete.

    This service delegates the row-locking work to Cart.merge_from(), keeping
    DRF views thin and making login/checkout reconciliation idempotent.
    """
    # ── Service-layer RBAC guard — client-only operation ─────────────────────
    # Silently discard session cart for non-client users.
    # DO NOT raise — caller gets the user's existing (empty) cart instead.
    user_role = str(getattr(user, "role", "") or getattr(user, "user_type", "") or "").lower()
    if user_role and user_role not in ("client", ""):
        logger.info(
            "[CartService] merge_anonymous_cart_session blocked: user_id=%s role=%s "
            "(RBAC guard — client-only operation; discarding anonymous session cart)",
            getattr(user, "pk", "?"),
            user_role,
        )
        return get_or_create_cart(user=user)
    # ─────────────────────────────────────────────────────────────────────────

    if not session_key:
        return get_or_create_cart(user=user)
    return Cart.merge_from(session_key=str(session_key)[:40], user=user)


@transaction.atomic
def discard_anonymous_cart_session(*, session_key: str | None) -> bool:
    """Delete a persisted anonymous cart when the current role cannot own it."""
    if not session_key:
        return False
    deleted, _ = Cart.objects.select_for_update().filter(
        session_key=str(session_key)[:40],
        user__isnull=True,
    ).delete()
    return deleted > 0
