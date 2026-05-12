"""Cart & Checkout domain audit helper — Wave B5."""
from __future__ import annotations


def log_cart_item_added(*, actor, cart_id: str, product_id: str, quantity: int = 1, request=None) -> None:
    """Record a cart item addition.

    Args:
        actor: The user adding to cart.
        cart_id: Cart PK as string.
        product_id: Product/ProductVariant PK.
        quantity: Quantity added.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.CART_ITEM_ADDED,
        event_category=EventCategory.CART,
        action=f"Cart item added: cart={cart_id} product={product_id} qty={quantity}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Cart",
        resource_id=cart_id,
        request=request,
        new_values={"product_id": product_id, "quantity": quantity},
    )


def log_cart_item_removed(*, actor, cart_id: str, product_id: str, request=None) -> None:
    """Record a cart item removal.

    Args:
        actor: The user removing the item.
        cart_id: Cart PK.
        product_id: Product/ProductVariant PK.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.CART_ITEM_REMOVED,
        event_category=EventCategory.CART,
        action=f"Cart item removed: cart={cart_id} product={product_id}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Cart",
        resource_id=cart_id,
        request=request,
        old_values={"product_id": product_id},
    )


def log_checkout_initiated(*, actor, cart_id: str, total: str, currency: str = "NGN", request=None) -> None:
    """Record a checkout initiation.

    Args:
        actor: The user starting checkout.
        cart_id: Cart PK.
        total: Order total as string.
        currency: ISO 4217 code.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.CHECKOUT_INITIATED,
        event_category=EventCategory.CART,
        action=f"Checkout initiated: cart={cart_id} total={total} {currency}",
        actor=actor,
        resource_type="Cart",
        resource_id=cart_id,
        request=request,
        new_values={"total": total, "currency": currency},
        is_compliance=True,
        retention_days=-1,
    )


def log_checkout_completed(*, actor, order_id: str, cart_id: str, request=None) -> None:
    """Record a completed checkout (order placed).

    Args:
        actor: The user who completed checkout.
        order_id: New Order PK.
        cart_id: Source Cart PK.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.CHECKOUT_COMPLETED,
        event_category=EventCategory.CART,
        action=f"Checkout completed: cart={cart_id} → order={order_id}",
        actor=actor,
        resource_type="Order",
        resource_id=order_id,
        request=request,
        new_values={"cart_id": cart_id, "order_id": order_id},
        is_compliance=True,
        retention_days=-1,
    )


def log_coupon_applied(*, actor, cart_id: str, coupon_code: str, discount: str, request=None) -> None:
    """Record a coupon being applied at checkout.

    Args:
        actor: The user applying the coupon.
        cart_id: Cart PK.
        coupon_code: The coupon code string.
        discount: Discount amount as string.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.COUPON_APPLIED,
        event_category=EventCategory.CART,
        action=f"Coupon applied: code={coupon_code} discount={discount} on cart={cart_id}",
        actor=actor,
        resource_type="Cart",
        resource_id=cart_id,
        request=request,
        new_values={"coupon_code": coupon_code, "discount": discount},
    )
