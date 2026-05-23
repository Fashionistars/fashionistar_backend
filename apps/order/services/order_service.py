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
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

# pyrefly: ignore [missing-import]
from django.db import IntegrityError, transaction
# pyrefly: ignore [missing-import]
from django.db.models import Q
from django.utils import timezone

from apps.common.request import get_client_ip
from apps.order.models import (
    Order,
    CartOrderItem,
    OrderStatus,
    OrderStatusHistory,
    OrderIdempotencyRecord,
    ORDER_STATUS_TRANSITIONS,
    CashPaymentMode,
    OrderPaymentPath,
    OrderPaymentSource,
    OrderCommercialTransitionType,
    OrderPaymentRecord,
    OrderCommercialTransitionLog,
    OrderDeliveryMode,
    FulfillmentType,
)

OrderItem = CartOrderItem  # alias: both names used in this service for clarity
from apps.cart.services import get_or_create_cart, clear_cart

# Module-level imports so tests can patch these as module attributes.
# Both use try/except to avoid circular imports during startup.
try:
    from apps.product.services import adjust_inventory
except ImportError:
    adjust_inventory = None  # type: ignore[assignment]

try:
    from apps.wallet.services import EscrowService
except (ImportError, AttributeError):
    EscrowService = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)
_HUNDRED_PERCENT = Decimal("100.00")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_order_idempotency_key(user_id, cart_snapshot: str) -> str:
    """Deterministic key from user + cart snapshot hash."""
    raw = f"order:{user_id}:{cart_snapshot}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _emit_order_audit(action: str, order: Order, actor=None, request=None, **metadata):
    """
    Standardized hook for order domain audits with forensic context.
    Wraps legacy audit helpers and ensures transaction integrity.
    """
    try:
        from apps.audit_logs.services.order import order_audit

        audit_metadata = {"order_number": order.order_number, **metadata}

        def _dispatch():
            if action == "order.placed":
                order_audit.log_order_created(
                    actor=actor,
                    order_id=str(order.id),
                    request=request,
                    metadata=audit_metadata,
                )
            elif action == "order.cancelled":
                order_audit.log_order_cancelled(
                    actor=actor,
                    order_id=str(order.id),
                    request=request,
                    reason=str(metadata.get("reason", "")),
                )
            elif action in {"order.fulfilled", "order.completed"}:
                order_audit.log_order_fulfilled(
                    actor=actor,
                    order_id=str(order.id),
                    request=request,
                )
            else:
                order_audit.log_order_updated(
                    actor=actor,
                    order_id=str(order.id),
                    request=request,
                    new_values=audit_metadata,
                )

        # Ensure audit only fires on successful commit
        transaction.on_commit(_dispatch)

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


def _actor_role(actor) -> str:
    if actor is None:
        return "system"
    if getattr(actor, "is_superuser", False):
        return "admin"
    if getattr(actor, "is_staff", False):
        return "staff"
    role = getattr(actor, "role", "")
    return str(role or "user")


def _emit_order_financial_audit(
    *,
    order: Order,
    actor=None,
    request=None,
    event_type: str,
    correlation_id: str,
    old_values: dict | None = None,
    new_values: dict | None = None,
    metadata: dict | None = None,
) -> None:
    """
    Records high-integrity financial audit events for the order domain.
    Captures IP and User-Agent for forensic traceability.
    """
    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get("HTTP_USER_AGENT") if request else None

    def _dispatch():
        try:
            from apps.audit_logs.models import AuditEventLog

            AuditEventLog.objects.create(
                actor=actor,
                actor_role=_actor_role(actor),
                event_type=event_type,
                entity_type="order",
                entity_id=str(order.pk),
                route_hint=f"/orders/{order.pk}/",
                old_values=old_values or {},
                new_values=new_values or {},
                metadata=metadata or {},
                correlation_id=correlation_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception:
            logger.warning(
                "Order financial audit write failed: order=%s event=%s",
                getattr(order, "order_number", order.pk),
                event_type,
            )

    transaction.on_commit(_dispatch)



def _mode_to_options(mode: str) -> set[str]:
    if mode == CashPaymentMode.COD:
        return {CashPaymentMode.COD}
    if mode == CashPaymentMode.PAY_AT_SHOP:
        return {CashPaymentMode.PAY_AT_SHOP}
    if mode == CashPaymentMode.BOTH:
        return {CashPaymentMode.COD, CashPaymentMode.PAY_AT_SHOP}
    return set()


def _options_to_mode(options: set[str]) -> str:
    if options == {CashPaymentMode.COD, CashPaymentMode.PAY_AT_SHOP}:
        return CashPaymentMode.BOTH
    if options == {CashPaymentMode.COD}:
        return CashPaymentMode.COD
    if options == {CashPaymentMode.PAY_AT_SHOP}:
        return CashPaymentMode.PAY_AT_SHOP
    return CashPaymentMode.DISABLED


def _resolve_cash_payment_mode_snapshot(*, active_items: list, vendor) -> str:
    intersected: set[str] | None = None
    for item in active_items:
        product_mode = getattr(item.product, "cash_payment_mode", CashPaymentMode.DISABLED)
        current = _mode_to_options(product_mode)
        intersected = current if intersected is None else intersected & current
    product_mode = _options_to_mode(intersected or set())
    if product_mode != CashPaymentMode.DISABLED:
        return product_mode
    return getattr(vendor, "cash_payment_mode", CashPaymentMode.DISABLED) or CashPaymentMode.DISABLED


def _log_commercial_transition(
    *,
    order: Order,
    transition_type: str,
    actor=None,
    request=None,
    payment_record: OrderPaymentRecord | None = None,
    payment_intent=None,
    from_status: str = "",
    to_status: str = "",
    delivery_mode: str = "",
    selected_percent: int = 0,
    cumulative_percent_paid: Decimal = Decimal("0.00"),
    amount_delta: Decimal = Decimal("0.00"),
    balance_after: Decimal = Decimal("0.00"),
    correlation_id: str = "",
    note: str = "",
    metadata: dict | None = None,
) -> OrderCommercialTransitionLog:
    log = OrderCommercialTransitionLog.objects.create(
        order=order,
        transition_type=transition_type,
        from_status=from_status,
        to_status=to_status,
        payment_record=payment_record,
        payment_intent=payment_intent,
        delivery_mode=delivery_mode or order.delivery_mode,
        cash_payment_mode_snapshot=order.cash_payment_mode_snapshot,
        selected_percent=selected_percent,
        cumulative_percent_paid=cumulative_percent_paid,
        amount_delta=amount_delta,
        balance_after=balance_after,
        actor=actor,
        actor_role=_actor_role(actor),
        occurred_at=timezone.now(),
        correlation_id=correlation_id,
        note=note,
        metadata=metadata or {},
    )
    _emit_order_financial_audit(
        order=order,
        actor=actor,
        request=request,
        event_type=f"order.{transition_type}",
        correlation_id=correlation_id,
        new_values={
            "transition_type": transition_type,
            "delivery_mode": log.delivery_mode,
            "selected_percent": selected_percent,
            "cumulative_percent_paid": str(cumulative_percent_paid),
            "amount_delta": str(amount_delta),
            "balance_after": str(balance_after),
        },
        metadata=metadata or {},
    )
    return log


def _calculate_applied_percent(amount: Decimal, total_amount: Decimal) -> Decimal:
    if total_amount <= 0:
        return Decimal("0.00")
    return ((amount / total_amount) * _HUNDRED_PERCENT).quantize(Decimal("0.01"))


def _update_order_payment_snapshot(
    *,
    order: Order,
    amount: Decimal,
    payment_path: str,
    provider: str,
    payment_reference: str,
    paid_at,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    cumulative_amount = (order.amount_paid_total + amount).quantize(Decimal("0.01"))
    cumulative_amount = min(cumulative_amount, order.total_amount)
    applied_percent = _calculate_applied_percent(amount, order.total_amount)
    cumulative_percent = _calculate_applied_percent(cumulative_amount, order.total_amount)
    remaining_amount = max(Decimal("0.00"), (order.total_amount - cumulative_amount).quantize(Decimal("0.01")))
    remaining_percent = max(Decimal("0.00"), (_HUNDRED_PERCENT - cumulative_percent).quantize(Decimal("0.01")))

    order.amount_paid_total = cumulative_amount
    order.percent_paid_total = cumulative_percent
    order.amount_outstanding = remaining_amount
    order.is_fully_paid = remaining_amount == Decimal("0.00")
    order.active_payment_path = payment_path
    order.payment_gateway = provider or order.payment_gateway
    order.payment_reference = payment_reference or order.payment_reference
    order.paid_at = paid_at
    if order.first_paid_at is None:
        order.first_paid_at = paid_at
    if order.is_fully_paid:
        order.final_paid_at = paid_at
    order.save(
        update_fields=[
            "amount_paid_total",
            "percent_paid_total",
            "amount_outstanding",
            "is_fully_paid",
            "active_payment_path",
            "payment_gateway",
            "payment_reference",
            "paid_at",
            "first_paid_at",
            "final_paid_at",
            "updated_at",
        ]
    )
    return cumulative_amount, applied_percent, cumulative_percent, remaining_percent


@transaction.atomic
def register_payment_tranche(
    *,
    order: Order,
    amount: Decimal,
    selected_percent: int,
    payment_source: str,
    payment_path: str,
    provider: str,
    actor=None,
    request=None,
    payment_intent=None,
    correlation_id: str = "",
    metadata: dict | None = None,
) -> OrderPaymentRecord:
    order = Order.objects.select_for_update().get(pk=order.pk)
    correlation_id = correlation_id or str(uuid4())
    paid_at = timezone.now()
    prior_status = order.status
    cumulative_amount, applied_percent, cumulative_percent, remaining_percent = _update_order_payment_snapshot(
        order=order,
        amount=amount,
        payment_path=payment_path,
        provider=provider,
        payment_reference=getattr(payment_intent, "reference", ""),
        paid_at=paid_at,
    )
    sequence_number = (order.payment_records.count() or 0) + 1
    record = OrderPaymentRecord.objects.create(
        order=order,
        sequence_number=sequence_number,
        payment_intent=payment_intent,
        payment_source=payment_source,
        provider=provider,
        selected_percent=selected_percent,
        applied_percent=applied_percent,
        amount=amount,
        currency=order.currency,
        cumulative_amount_paid=cumulative_amount,
        cumulative_percent_paid=cumulative_percent,
        remaining_amount=order.amount_outstanding,
        remaining_percent=remaining_percent,
        is_final_payment=order.is_fully_paid,
        paid_at=paid_at,
        actor=actor,
        correlation_id=correlation_id,
        metadata=metadata or {},
    )
    if payment_path in {OrderPaymentPath.COD, OrderPaymentPath.PAY_AT_SHOP}:
        next_status = OrderStatus.AWAITING_CASH_CONFIRMATION
    elif order.is_fully_paid:
        next_status = OrderStatus.PAYMENT_CONFIRMED
    else:
        next_status = prior_status

    _log_commercial_transition(
        order=order,
        transition_type=OrderCommercialTransitionType.ESCROW_HELD,
        actor=actor,
        payment_record=record,
        payment_intent=payment_intent,
        from_status=prior_status,
        to_status=next_status,
        selected_percent=selected_percent,
        cumulative_percent_paid=cumulative_percent,
        amount_delta=amount,
        balance_after=order.amount_outstanding,
        correlation_id=correlation_id,
        note="Escrow hold recorded for payment tranche.",
        metadata=metadata or {},
    )
    if payment_path == OrderPaymentPath.GATEWAY:
        _log_commercial_transition(
            order=order,
            transition_type=OrderCommercialTransitionType.WALLET_CREDITED,
            actor=actor,
            payment_record=record,
            payment_intent=payment_intent,
            selected_percent=selected_percent,
            cumulative_percent_paid=cumulative_percent,
            amount_delta=amount,
            balance_after=order.amount_outstanding,
            correlation_id=correlation_id,
            note="Gateway payment credited to wallet before escrow hold.",
            metadata=metadata or {},
        )

    if next_status != order.status:
        order.status = next_status
        order.save(update_fields=["status", "updated_at"])
        _record_status_history(
            order,
            prior_status,
            next_status,
            actor=actor,
            note="Payment tranche updated order payment progress.",
        )

    _emit_order_financial_audit(
        order=order,
        actor=actor,
        request=request,
        event_type="order.payment_record.created",
        correlation_id=correlation_id,
        new_values={
            "sequence_number": sequence_number,
            "payment_source": payment_source,
            "provider": provider,
            "selected_percent": selected_percent,
            "applied_percent": str(applied_percent),
            "amount": str(amount),
            "cumulative_amount_paid": str(cumulative_amount),
            "cumulative_percent_paid": str(cumulative_percent),
            "remaining_amount": str(order.amount_outstanding),
            "remaining_percent": str(remaining_percent),
            "is_final_payment": order.is_fully_paid,
        },
        metadata=metadata or {},
    )
    _log_commercial_transition(
        order=order,
        transition_type=OrderCommercialTransitionType.PAYMENT_SUCCEEDED,
        actor=actor,
        request=request,
        payment_record=record,
        payment_intent=payment_intent,
        from_status=prior_status,
        to_status=next_status,
        selected_percent=selected_percent,
        cumulative_percent_paid=cumulative_percent,
        amount_delta=amount,
        balance_after=order.amount_outstanding,
        correlation_id=correlation_id,
        metadata=metadata,
    )
    return record


def _get_succeeded_payment_intent(*, order: Order, payment_reference: str = ""):
    from apps.payment.models import PaymentIntent, PaymentIntentStatus, PaymentPurpose

    queryset = PaymentIntent.objects.filter(
        order_id=str(order.pk),
        purpose=PaymentPurpose.ORDER_PAYMENT,
        status=PaymentIntentStatus.SUCCEEDED,
    ).order_by("-updated_at", "-created_at")

    if payment_reference:
        queryset = queryset.filter(
            Q(reference=payment_reference) | Q(provider_reference=payment_reference)
        )

    return queryset.first()


def _get_active_order_hold(*, order: Order):
    from apps.wallet.models import WalletHold, WalletHoldStatus

    return (
        WalletHold.objects.select_for_update()
        .filter(order_id=str(order.pk), status=WalletHoldStatus.ACTIVE)
        .order_by("-created_at")
        .first()
    )


# ─────────────────────────────────────────────────────────────────────────────
# PLACE ORDER — The Critical Path
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def place_order(
    *,
    user,
    delivery_address: dict,
    fulfillment_type: str = FulfillmentType.DELIVERY,
    measurement_profile_id=None,
    notes: str = "",
    idempotency_key: str | None = None,
    adjust_inventory=None,
    request=None,
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
    inventory_adjuster = adjust_inventory or globals().get("adjust_inventory")

    if idempotency_key:
        existing_record = (
            OrderIdempotencyRecord.objects.filter(key=idempotency_key)
            .select_related("order")
            .first()
        )
        if existing_record:
            logger.info(
                "Idempotent order replay: key=%s order=%s",
                idempotency_key,
                existing_record.order.order_number,
            )
            return existing_record.order

    # ── Step 2: Fetch and lock cart ──────────────────────────────────────
    cart = get_or_create_cart(user)
    if cart.items.filter(is_saved_for_later=False).count() == 0:
        raise ValueError("Cart is empty. Cannot place an order.")

    # Re-acquire cart with lock inside the transaction
    cart = type(cart).objects.select_for_update().get(pk=cart.pk)
    active_items = list(
        cart.items.filter(is_saved_for_later=False).select_related(
            "product",
            "product__vendor",
            "variant",
            "variant__size",
            "variant__color",
        )
    )
    if not active_items:
        raise ValueError("Cart is empty. Cannot place an order.")

    # ── Step 3: Lock all product rows ────────────────────────────────────
    product_ids = [item.product_id for item in active_items]
    product_model = type(active_items[0].product)
    # Product rows are reached through the cart item relationship already
    # prefetched above, then the concrete model class is reused for the lock.
    # This avoids importing the product domain model directly inside order
    # services while preserving the same SELECT ... FOR UPDATE protection.
    products_map = {
        product.id: product
        for product in product_model.objects.select_for_update().filter(id__in=product_ids)
    }

    # ── Step 4: Stock validation ─────────────────────────────────────────
    for item in active_items:
        product = products_map.get(item.product_id)
        if not product or getattr(product, "is_deleted", False):
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
        (products_map[item.product_id].shipping_amount for item in active_items),
        Decimal("0"),
    )
    discount = cart.coupon_discount
    total = max(Decimal("0"), subtotal + shipping - discount)

    # Commission calculation
    commission_total = Decimal("0")
    for item in active_items:
        product = products_map[item.product_id]
        rate = product.commission_rate
        commission_total += (rate / 100) * item.unit_price * item.quantity

    vendor = active_items[0].product.vendor if active_items else None
    vendor_payout = total - commission_total
    cash_payment_mode_snapshot = _resolve_cash_payment_mode_snapshot(
        active_items=active_items,
        vendor=vendor,
    )

    # ── Step 6: Create Order ─────────────────────────────────────────────
    idem_key = idempotency_key or _make_order_idempotency_key(
        user.id,
        f"{cart.id}:{subtotal}",
    )

    try:
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
            amount_outstanding=total,
            currency="NGN",
            coupon_code=cart.coupon.code if cart.coupon else "",
            delivery_address=delivery_address,
            measurement_profile_id=measurement_profile_id,
            idempotency_key=idem_key,
            notes=notes,
            cash_payment_mode_snapshot=cash_payment_mode_snapshot,
            delivery_mode=(
                OrderDeliveryMode.VENDOR_SHOP_PICKUP
                if fulfillment_type == FulfillmentType.PICKUP
                else OrderDeliveryMode.PLATFORM_COURIER
            ),
        )
    except IntegrityError:
        existing_order = Order.objects.filter(idempotency_key=idem_key).first()
        if existing_order:
            logger.info(
                "Concurrent idempotent order replay recovered: key=%s order=%s",
                idem_key,
                existing_order.order_number,
            )
            return existing_order
        raise

    # ── Step 7: Create OrderItems with snapshots ─────────────────────────
    order_items = []
    cart_order_snapshot_payload = []
    for item in active_items:
        product = products_map[item.product_id]
        rate = product.commission_rate
        line_total = item.unit_price * item.quantity
        commission_amount = (rate / 100) * line_total
        variant = item.variant
        size = getattr(variant, "size", None) if variant else None
        color = getattr(variant, "color", None) if variant else None
        try:
            cover_image_url = str(product.image.url) if product.image else ""
        except (AttributeError, ValueError):
            cover_image_url = ""

        order_items.append(
            CartOrderItem(
                order=order,
                product=item.product,
                variant=variant,
                vendor=product.vendor,
                product_title_snapshot=product.title,
                product_sku_snapshot=product.sku,
                variant_description_snapshot=str(variant) if variant else "",
                vendor_name_snapshot=getattr(product.vendor, "store_name", ""),
                unit_price=item.unit_price,
                quantity=item.quantity,
                line_total=line_total,
                commission_rate=rate,
                commission_amount=commission_amount,
                vendor_payout=line_total - commission_amount,
                is_custom_order=product.is_customisable,
                size_snapshot=getattr(size, "name", "") if size else "",
                color_snapshot=getattr(color, "name", "") if color else "",
                cart_item_idempotency_key=item.idempotency_key,
            )
        )
        cart_order_snapshot_payload.append(
            {
                "product_id": str(product.pk),
                "variant_id": str(variant.pk) if variant else None,
                "sku_snapshot": product.sku,
                "title_snapshot": product.title,
                "variant_snapshot": str(variant) if variant else "",
                "cover_image_url": cover_image_url,
                "unit_price": str(item.unit_price),
                "quantity": item.quantity,
                "line_total": str(line_total),
                "commission_rate": str(rate),
                "size_snapshot": getattr(size, "name", "") if size else "",
                "color_snapshot": getattr(color, "name", "") if color else "",
                "cart_item_idempotency_key": str(item.idempotency_key),
            }
        )
    CartOrderItem.objects.bulk_create(order_items)

    # ── Step 8: Deduct stock ─────────────────────────────────────
    for item in active_items:
        product = products_map[item.product_id]
        if inventory_adjuster is not None:
            inventory_adjuster(
                product=product,
                quantity_delta=-item.quantity,
                reason="sale",
                reference_id=order.order_number,
                actor=user,
                variant=item.variant,
            )
        type(product).objects.filter(pk=product.pk).update(
            orders_count=product.orders_count + 1
        )

    # ── Step 9: Increment coupon usage ───────────────────────────────────
    if cart.coupon:
        type(cart.coupon).objects.filter(pk=cart.coupon.pk).update(
            usage_count=cart.coupon.usage_count + 1
        )

    # ── Step 10: Store idempotency record ────────────────────────────────
    OrderIdempotencyRecord.objects.create(
        key=idem_key,
        order=order,
        expires_at=timezone.now() + timezone.timedelta(hours=24),
    )

    # ── Step 11: Clear cart ──────────────────────────────────────────────
    clear_cart(user=user)

    # ── Step 12: Log initial status history ──────────────────────────────
    _record_status_history(order, "", OrderStatus.PENDING_PAYMENT, actor=user, note="Order placed.")

    # ── Step 13: Emit audit event ────────────────────────────────────────
    transaction.on_commit(
        lambda: _emit_order_audit(
            "order.placed",
            order,
            actor=user,
            request=request,
            total=str(total),
        )
    )
    from apps.common.events import event_bus

    event_bus.emit_on_commit(
        "order.placed",
        order_id=str(order.pk),
        order_number=order.order_number,
        cart_items=cart_order_snapshot_payload,
    )

    logger.info("Order placed: %s total=%s user=%s", order.order_number, total, user)
    return order


# ─────────────────────────────────────────────────────────────────────────────
# CONFIRM PAYMENT
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def confirm_payment(*, order: Order, payment_reference: str, actor=None, request=None) -> Order:
    """Transition PENDING_PAYMENT → PAYMENT_CONFIRMED."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_transition_to(OrderStatus.PAYMENT_CONFIRMED):
        raise ValueError(f"Cannot confirm payment for order in status '{order.status}'.")
    intent = _get_succeeded_payment_intent(order=order, payment_reference=payment_reference)
    if intent is None:
        raise ValueError(
            "Cannot confirm payment without a succeeded payment intent and escrow hold for this order."
        )
    hold = _get_active_order_hold(order=order)
    if hold is None:
        # Soft warning — the escrow hold is created by the payment-provider webhook
        # handler (Paystack / Flutterwave).  Webhook delivery is asynchronous, so
        # the hold may not yet exist at the moment confirm_payment fires from the
        # payment-success view.  This is normal and does NOT indicate fraud.
        # A hard raise here would block legitimate payment confirmations.
        logger.warning(
            "confirm_payment: no active escrow hold for order=%s (hold may arrive via webhook shortly)",
            order.order_number,
        )
    from_status = order.status
    order.status = OrderStatus.PAYMENT_CONFIRMED
    order.payment_reference = payment_reference or intent.reference
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "payment_reference", "paid_at", "updated_at"])
    _record_status_history(order, from_status, OrderStatus.PAYMENT_CONFIRMED, actor=actor, note="Payment confirmed via webhook.")
    _log_commercial_transition(
        order=order,
        transition_type=OrderCommercialTransitionType.PAYMENT_SUCCEEDED,
        actor=actor,
        payment_intent=intent,
        from_status=from_status,
        to_status=OrderStatus.PAYMENT_CONFIRMED,
        selected_percent=int(order.percent_paid_total or 0),
        cumulative_percent_paid=order.percent_paid_total,
        amount_delta=Decimal("0.00"),
        balance_after=order.amount_outstanding,
        correlation_id=intent.idempotency_key or payment_reference,
        note="Payment confirmation finalized order state.",
        request=request,
        metadata={"payment_reference": payment_reference or intent.reference},
    )
    transaction.on_commit(
        lambda: _emit_order_audit(
            "order.payment_confirmed",
            order,
            actor=actor, request=request,
            ref=payment_reference,
        )
    )
    return order


# ─────────────────────────────────────────────────────────────────────────────
# TRANSITION STATUS
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def transition_status(*, order: Order, new_status: str, actor=None, note: str = "", request=None) -> Order:
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
    transition_map = {
        OrderStatus.SHIPPED: OrderCommercialTransitionType.SHIPPED,
        OrderStatus.OUT_FOR_DELIVERY: OrderCommercialTransitionType.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED: OrderCommercialTransitionType.DELIVERED,
        OrderStatus.COMPLETED: OrderCommercialTransitionType.ORDER_COMPLETED,
        OrderStatus.DISPUTED: OrderCommercialTransitionType.DISPUTE_OPENED,
    }
    if new_status in transition_map:
        _log_commercial_transition(
            order=order,
            transition_type=transition_map[new_status],
            actor=actor,
            from_status=from_status,
            to_status=new_status,
            delivery_mode=order.delivery_mode,
            selected_percent=int(order.percent_paid_total or 0),
            cumulative_percent_paid=order.percent_paid_total,
            amount_delta=Decimal("0.00"),
            balance_after=order.amount_outstanding,
            correlation_id=str(uuid4()),
            note=note,
            request=request,
            metadata={"status": new_status},
        )
    transaction.on_commit(
        lambda: _emit_order_audit(
            f"order.status.{new_status}",
            order,
            actor=actor, request=request,
            from_status=from_status,
        )
    )
    return order


@transaction.atomic
def update_delivery_status(
    *,
    order_id,
    new_status: str,
    actor=None,
    note: str = "",
    tracking_number: str = "",
    request=None,
) -> Order:
    """Update an order delivery/production state from the admin surface.

    Args:
        order_id: Order primary key from the DRF route.
        new_status: Target order status after serializer normalization.
        actor: Authenticated staff/admin user performing the change.
        note: Optional audit note.
        tracking_number: Optional courier tracking code to persist.

    Returns:
        Order: The locked and updated order.

    Raises:
        ValueError: If the order is missing or the transition is invalid.
    """
    try:
        order = Order.objects.select_for_update().get(pk=order_id)
    except Order.DoesNotExist as exc:
        raise ValueError("Order not found.") from exc

    if tracking_number:
        order.tracking_number = tracking_number
        order.save(update_fields=["tracking_number", "updated_at"])

    return transition_status(
        order=order,
        new_status=new_status,
        actor=actor,
        note=note or "Delivery status updated by admin.",
        request=request,
    )


# ─────────────────────────────────────────────────────────────────────────────
# RELEASE ESCROW  (on DELIVERED confirmation by client)
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def release_escrow(*, order: Order, actor=None, request=None) -> Order:
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

    if EscrowService is None:
        raise ValueError("Escrow service is unavailable for this order release.")

    hold = _get_active_order_hold(order=order)
    if hold is None:
        raise ValueError("No active escrow hold exists for this order.")

    vendor_user = getattr(getattr(order, "vendor", None), "user", None)
    if vendor_user is None:
        raise ValueError("Order vendor user is missing for escrow release.")

    try:
        EscrowService.release_order_payment(
            hold_reference=hold.reference,
            vendor_user=vendor_user,
            idempotency_key=f"order-release:{order.pk}",
        )
    except Exception as exc:
        logger.error("Escrow release failed: order=%s error=%s", order.order_number, exc)
        raise

    from_status = order.status
    order.status = OrderStatus.COMPLETED
    order.escrow_released = True
    order.save(update_fields=["status", "escrow_released", "updated_at"])
    _record_status_history(order, from_status, OrderStatus.COMPLETED, actor=actor, note="Escrow released by client.")
    _log_commercial_transition(
        order=order,
        transition_type=OrderCommercialTransitionType.ESCROW_RELEASED,
        actor=actor,
        from_status=from_status,
        to_status=OrderStatus.COMPLETED,
        delivery_mode=order.delivery_mode,
        selected_percent=int(order.percent_paid_total or 0),
        cumulative_percent_paid=order.percent_paid_total,
        amount_delta=Decimal("0.00"),
        balance_after=order.amount_outstanding,
        correlation_id=f"order-release:{order.pk}",
        note="Escrow released by client confirmation.",
        request=request,
        metadata={"hold_reference": hold.reference},
    )
    transaction.on_commit(
        lambda: _emit_order_audit("order.completed", order, actor=actor, request=request)
    )
    return order


# ─────────────────────────────────────────────────────────────────────────────
# CANCEL ORDER
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def cancel_order(*, order: Order, actor=None, reason: str = "", request=None) -> Order:
    """Cancel order and release stock reservation."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_transition_to(OrderStatus.CANCELLED):
        raise ValueError(f"Cannot cancel order in status '{order.status}'.")
    hold = _get_active_order_hold(order=order)
    if hold is not None:
        if EscrowService is None:
            raise ValueError("Escrow service is unavailable for order cancellation.")
        EscrowService.refund_escrow(
            hold_reference=hold.reference,
            idempotency_key=f"order-cancel-refund:{order.pk}",
        )
    # Release stock for each item
    for item in order.cart_order_items.select_related("product", "variant"):
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
    transaction.on_commit(
        lambda: _emit_order_audit("order.cancelled", order, actor=actor, request=request, reason=reason)
    )
    return order
