# apps/order/models/__init__.py
from apps.order.models.discount_code import DiscountCode
from apps.order.models.order import (
    OrderStatus,
    ORDER_STATUS_TRANSITIONS,
    CashPaymentMode,
    CartOrderItem,
    FulfillmentType,
    Order,
    OrderCommercialTransitionLog,
    OrderCommercialTransitionType,
    OrderDeliveryMode,
    OrderIdempotencyRecord,
    OrderPaymentPath,
    OrderPaymentRecord,
    OrderPaymentSource,
    OrderStatusHistory
)

from apps.order.models.order_dispute import OrderDispute
from apps.order.models.order_timeline import OrderTimeline

# CustomOrder domain has been extracted to apps.custom_order.
# Import here for backwards-compatibility only — use apps.custom_order directly
# in new code.
from apps.custom_order.models import (  # noqa: F401
    CustomOrder,
    CustomOrderMilestone,
    CustomOrderStatus,
    MilestonePaymentStatus,
    MILESTONE_PERCENTAGES,
)

__all__ = [
    "OrderStatus",
    "FulfillmentType",
    "CashPaymentMode",
    "OrderDeliveryMode",
    "OrderPaymentPath",
    "OrderPaymentSource",
    "OrderCommercialTransitionType",
    "ORDER_STATUS_TRANSITIONS",
    "OrderIdempotencyRecord",
    "Order",
    "CartOrderItem",
    "OrderStatusHistory",
    "OrderPaymentRecord",
    "OrderCommercialTransitionLog",
    # 2026 — Phase 4 additions
    "OrderTimeline",
    "OrderDispute",
    "DiscountCode",
    # Custom Order — re-exported for backwards compat; canonical location: apps.custom_order
    "CustomOrder",
    "CustomOrderMilestone",
    "CustomOrderStatus",
    "MilestonePaymentStatus",
    "MILESTONE_PERCENTAGES",
]
