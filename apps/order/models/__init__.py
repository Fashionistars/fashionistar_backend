# apps/order/models/__init__.py
from apps.order.models.order import (
    OrderStatus,
    FulfillmentType,
    CashPaymentMode,
    OrderDeliveryMode,
    OrderPaymentPath,
    OrderPaymentSource,
    OrderCommercialTransitionType,
    ORDER_STATUS_TRANSITIONS,
    OrderIdempotencyRecord,
    Order,
    CartOrderItem,
    OrderStatusHistory,
    OrderPaymentRecord,
    OrderCommercialTransitionLog,
)

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
    # Custom Order — re-exported for backwards compat; canonical location: apps.custom_order
    "CustomOrder",
    "CustomOrderMilestone",
    "CustomOrderStatus",
    "MilestonePaymentStatus",
    "MILESTONE_PERCENTAGES",
]
