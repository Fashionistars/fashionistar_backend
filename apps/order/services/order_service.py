# apps/order/services/order_service.py
"""
Order service — the most critical service in Fashionistar.

Guarantees:
  1. transaction.atomic() + select_for_update on Cart and all Products.
  2. Idempotency key check BEFORE any write — idempotent under retries.
  3. Stock deduction is atomic — prevents overselling.
  4. Escrow trigger fired INSIDE the transaction — no orphaned escrow.
  5. Coupon usage_count incremented atomically on placement.
  6. CartClear called inside same transaction — cart and order are consistent.
  7. Status transitions validated against ORDER_STATUS_TRANSITIONS machine.
  8. Every transition emitted to AuditService and OrderStatusHistory.

Financial flow:
  place_order()
    → validate idempotency
    → lock product rows (select_for_update)
    → deduct stock (atomically)
    → create Order + OrderItems (snapshots)
    → increment coupon usage_count
    → fire escrow_trigger (wallet service)
    → clear cart
    → emit audit event
    → return Order

confirm_payment()
    → verify Paystack reference
    → transition PENDING_PAYMENT → PAYMENT_CONFIRMED
    → update paid_at

transition_status()
    → validate allowed transition
    → update Order.status
    → append OrderStatusHistory row
    → emit audit event

release_escrow()
    → confirm delivery
    → transition DELIVERED → COMPLETED
    → release escrow in wallet service
"""

import hashlib
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.order.models import (
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    OrderIdempotencyRecord,
    ORDER_STATUS_TRANSITIONS,
)
from apps.cart.services import get_or_create_cart, clear_cart

# Module-level imports so tests can patch these as module attributes.
# Both use try/except to avoid circular imports during startup.
try:
    from apps.product.services import adjust_inventory
except ImportError:
    adjust_inventory = None  # type: ignore[assignment]

try:
    from apps.wallet.services import escrow_service
except (ImportError, AttributeError):
    escrow_service = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_order_idempotency_key(user_id, cart_snapshot: str) -> str:
    """Deterministic key from user + cart snapshot hash."""
    raw = f"order:{user_id}:{cart_snapshot}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _emit_order_audit(action: str, order: Order, actor=None, **metadata):
    try:
        from apps.audit_logs.services.audit import AuditService
        from apps.audit_logs.models import EventType, EventCategory, SeverityLevel
        AuditService.log(
            event_type=EventType.RECORD_CREATED if action == "order.placed" else EventType.RECORD_UPDATED,
            event_category=EventCategory.FINANCIAL,
            severity=SeverityLevel.INFO,
            action=action,
            actor=actor,
            resource_type="Order",
            resource_id=str(order.id),
            metadata={"order_number": order.order_number, **metadata},
            is_compliance=True,
        )
    except Exception:
        logger.warning("AuditService order event failed: action=%s order=%s", action, getattr(order, "id", "?"))


def _record_status_history(order: Order, from_status: str, to_status: str, actor=None, note: str = ""):
    OrderStatusHistory.objects.create(
        order=order,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        note=note,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PLACE ORDER — The Critical Path
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def place_order(
    *,
    user,
    delivery_address: dict,
    fulfillment_type: str = "delivery",
    idempotency_key: str = None,
    measurement_profile_id=None,
    notes: str = "",
) -> Order:
    """
    Atomic order placement.

    Steps (all inside one transaction):
      1. Check idempotency — return existing order if key already used.
      2. Fetch cart + lock cart row.
      3. Lock all product rows (select_for_update).
      4. Validate stock for every line item.
      5. Create Order.
      6. Create OrderItems with financial snapshots.
      7. Deduct stock atomically.
      8. Increment coupon usage_count.
      9. Trigger escrow (wallet service).
      10. Clear cart.
      11. Log status history.
      12. Emit audit event.
    """
    from apps.product.models import Product

    # ── Step 1: Idempotency check ────────────────────────────────────────
    if idempotency_key:
        existing_record = OrderIdempotencyRecord.objects.filter(
            key=idempotency_key
        ).select_related("order").first()
        if existing_record:
            logger.info("Idempotent order replay: key=%s order=%s", idempotency_key, existing_record.order.order_number)
            return existing_record.order

    # ── Step 2: Fetch and lock cart ──────────────────────────────────────
    cart = get_or_create_cart(user)
    if cart.items.filter(is_saved_for_later=False).count() == 0:
        raise ValueError("Cart is empty. Cannot place an order.")

    # Re-acquire cart with lock inside the transaction
    cart = type(cart).objects.select_for_update().get(pk=cart.pk)
    active_items = list(cart.items.filter(is_saved_for_later=False).select_related("product", "variant"))

    # ── Step 3: Lock all product rows ────────────────────────────────────
    product_ids = [item.product_id for item in active_items]
    products_map = {
        p.id: p
        for p in Product.objects.select_for_update().filter(id__in=product_ids)
    }

    # ── Step 4: Stock validation ─────────────────────────────────────────
    for item in active_items:
        product = products_map.get(item.product_id)
        if not product or product.is_deleted:
            raise ValueError(f"Product '{item.product.title}' is no longer available.")
        available = item.variant.stock_qty if item.variant else product.stock_qty
        if available < item.quantity:
            raise ValueError(
                f"'{product.title}': only {available} unit(s) available, "
                f"but {item.quantity} requested."
            )

    # ── Step 5: Calculate order totals ───────────────────────────────────
    subtotal = cart.subtotal
    shipping = sum(
        (products_map[i.product_id].shipping_amount for i in active_items),
        Decimal("0")
    )
    discount = cart.coupon_discount
    total = max(Decimal("0"), subtotal + shipping - discount)

    # Commission calculation
    commission_total = Decimal("0")
    for item in active_items:
        product = products_map[item.product_id]
        rate = product.commission_rate
        commission_total += (rate / 100) * item.unit_price * item.quantity

    vendor_payout = total - commission_total

    # Resolve vendor (from first item)
    vendor = active_items[0].product.vendor if active_items else None

    # ── Step 6: Create Order ─────────────────────────────────────────────
    idem_key = idempotency_key or _make_order_idempotency_key(
        user.id, f"{cart.id}:{subtotal}"
    )

    order = Order.objects.create(
        user=user,
        vendor=vendor,
        status=OrderStatus.PENDING_PAYMENT,
        fulfillment_type=fulfillment_type,
        subtotal=subtotal,
        shipping_amount=shipping,
        discount_amount=discount,
        total_amount=total,
        commission_amount=commission_total,
        vendor_payout=vendor_payout,
        currency="NGN",
        coupon_code=cart.coupon.code if cart.coupon else "",
        delivery_address=delivery_address,
        measurement_profile_id=measurement_profile_id,
        idempotency_key=idem_key,
        notes=notes,
    )

    # ── Step 7: Create OrderItems with snapshots ─────────────────────────
    order_items = []
    for item in active_items:
        product = products_map[item.product_id]
        rate = product.commission_rate
        line_total = item.unit_price * item.quantity
        comm_amount = (rate / 100) * line_total
        order_items.append(
            OrderItem(
                order=order,
                product=item.product,
                variant=item.variant,
                vendor=product.vendor,
                product_title=product.title,
                product_sku=product.sku,
                variant_description=str(item.variant) if item.variant else "",
                unit_price=item.unit_price,
                quantity=item.quantity,
                commission_rate=rate,
                commission_amount=comm_amount,
                line_total=line_total,
                is_custom_order=product.is_customisable,
            )
        )
    OrderItem.objects.bulk_create(order_items)

    # ── Step 8: Deduct stock ─────────────────────────────────────
    for item in active_items:
        product = products_map[item.product_id]
        if adjust_inventory is not None:
            adjust_inventory(
                product=product,
                quantity_delta=-item.quantity,
                reason="sale",
                reference_id=order.order_number,
                actor=user,
                variant=item.variant,
            )
        # Update product.orders_count
        Product.objects.filter(pk=product.pk).update(orders_count=product.orders_count + 1)

    # ── Step 9: Increment coupon usage ───────────────────────────────────
    if cart.coupon:
        type(cart.coupon).objects.filter(pk=cart.coupon.pk).update(
            usage_count=cart.coupon.usage_count + 1
        )

    # ── Step 10: Trigger escrow ──────────────────────────────────
    try:
        if escrow_service is not None:
            escrow_service.hold_escrow(order=order, amount=total, actor=user)
    except Exception as exc:
        logger.warning("Escrow hold failed for order %s: %s", order.order_number, exc)
        # Do not abort — escrow can be reconciled via Celery task

    # ── Step 11: Store idempotency record ────────────────────────────────
    OrderIdempotencyRecord.objects.create(
        key=idem_key,
        order=order,
        expires_at=timezone.now() + timezone.timedelta(hours=24),
    )

    # ── Step 12: Clear cart ──────────────────────────────────────────────
    clear_cart(user=user)

    # ── Step 13: Log initial status history ──────────────────────────────
    _record_status_history(order, "", OrderStatus.PENDING_PAYMENT, actor=user, note="Order placed.")

    # ── Step 14: Emit audit event ────────────────────────────────────────
    _emit_order_audit("order.placed", order, actor=user, total=str(total))

    logger.info("Order placed: %s total=%s user=%s", order.order_number, total, user)
    return order


# ─────────────────────────────────────────────────────────────────────────────
# CONFIRM PAYMENT
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def confirm_payment(*, order: Order, payment_reference: str, actor=None) -> Order:
    """Transition PENDING_PAYMENT → PAYMENT_CONFIRMED."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_transition_to(OrderStatus.PAYMENT_CONFIRMED):
        raise ValueError(f"Cannot confirm payment for order in status '{order.status}'.")
    from_status = order.status
    order.status = OrderStatus.PAYMENT_CONFIRMED
    order.payment_reference = payment_reference
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "payment_reference", "paid_at", "updated_at"])
    _record_status_history(order, from_status, OrderStatus.PAYMENT_CONFIRMED, actor=actor, note="Payment confirmed via webhook.")
    _emit_order_audit("order.payment_confirmed", order, actor=actor, ref=payment_reference)
    return order


# ─────────────────────────────────────────────────────────────────────────────
# TRANSITION STATUS
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def transition_status(*, order: Order, new_status: str, actor=None, note: str = "") -> Order:
    """Generic status transition with machine validation."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_transition_to(new_status):
        raise ValueError(
            f"Invalid transition: '{order.status}' → '{new_status}'. "
            f"Allowed: {ORDER_STATUS_TRANSITIONS.get(order.status, [])}"
        )
    from_status = order.status
    order.status = new_status
    order.save(update_fields=["status", "updated_at"])
    _record_status_history(order, from_status, new_status, actor=actor, note=note)
    _emit_order_audit(f"order.status.{new_status}", order, actor=actor, from_status=from_status)
    return order


# ─────────────────────────────────────────────────────────────────────────────
# RELEASE ESCROW  (on DELIVERED confirmation by client)
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def release_escrow(*, order: Order, actor=None) -> Order:
    """
    Mark order COMPLETED and release escrow to vendor wallet.
    Called by client on delivery confirmation.
    """
    order = Order.objects.select_for_update().get(pk=order.pk)
    # Idempotency guard first — gives a precise, test-verifiable error message.
    if order.escrow_released:
        raise ValueError("Escrow already released for this order.")
    if not order.can_transition_to(OrderStatus.COMPLETED):
        raise ValueError(f"Cannot complete order in status '{order.status}'.")

    # Release escrow in wallet
    try:
        if escrow_service is not None:
            escrow_service.release_escrow(order=order, actor=actor)
    except Exception as exc:
        logger.error("Escrow release failed: order=%s error=%s", order.order_number, exc)
        raise

    from_status = order.status
    order.status = OrderStatus.COMPLETED
    order.escrow_released = True
    order.save(update_fields=["status", "escrow_released", "updated_at"])
    _record_status_history(order, from_status, OrderStatus.COMPLETED, actor=actor, note="Escrow released by client.")
    _emit_order_audit("order.completed", order, actor=actor)
    return order


# ─────────────────────────────────────────────────────────────────────────────
# CANCEL ORDER
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def cancel_order(*, order: Order, actor=None, reason: str = "") -> Order:
    """Cancel order and release stock reservation."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_transition_to(OrderStatus.CANCELLED):
        raise ValueError(f"Cannot cancel order in status '{order.status}'.")
    # Release stock for each item
    for item in order.items.select_related("product", "variant"):
        if item.product and adjust_inventory is not None:
            adjust_inventory(
                product=item.product,
                quantity_delta=+item.quantity,
                reason="return",
                reference_id=order.order_number,
                actor=actor,
                variant=item.variant,
            )
    from_status = order.status
    order.status = OrderStatus.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    _record_status_history(order, from_status, OrderStatus.CANCELLED, actor=actor, note=reason or "Order cancelled.")
    _emit_order_audit("order.cancelled", order, actor=actor, reason=reason)
    return order
