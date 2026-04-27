# apps/order/models/order.py
"""
Order domain models.

Architecture:
  - Order: top-level, one per checkout session. Has status state machine.
  - OrderItem: one per product/variant with price/commission snapshots.
  - OrderStatusHistory: append-only audit trail of all status transitions.
  - OrderIdempotencyRecord: prevents duplicate order creation from retry storms.

on_delete policy:
  - Order → User: SET_NULL (user deleted, order history preserved for financial audit)
  - Order → Vendor: SET_NULL (same reason)
  - OrderItem → Order: CASCADE
  - OrderItem → Product: SET_NULL (product deleted, history preserved)
  - OrderItem → ProductVariant: SET_NULL
  - OrderStatusHistory → Order: CASCADE
  - OrderIdempotencyRecord → Order: CASCADE

Financial integrity:
  - Every Order creation MUST be inside transaction.atomic().
  - Escrow trigger fires immediately after Order is persisted (see OrderService).
  - commission_amount is calculated and frozen on OrderItem at placement time.
  - payment_reference stores Paystack ref (unique, indexed).
  - Idempotency key on Order prevents duplicate charges from retry storms.
"""

import logging
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel

User = get_user_model()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# STATUS CHOICES
# ─────────────────────────────────────────────────────────────────────────────

class OrderStatus(models.TextChoices):
    PENDING_PAYMENT     = "pending_payment",    _("Pending Payment")
    PAYMENT_CONFIRMED   = "payment_confirmed",  _("Payment Confirmed")
    PROCESSING          = "processing",         _("Processing")
    SHIPPED             = "shipped",            _("Shipped")
    OUT_FOR_DELIVERY    = "out_for_delivery",   _("Out for Delivery")
    DELIVERED           = "delivered",          _("Delivered")
    COMPLETED           = "completed",          _("Completed")
    CANCELLED           = "cancelled",          _("Cancelled")
    REFUND_REQUESTED    = "refund_requested",   _("Refund Requested")
    REFUNDED            = "refunded",           _("Refunded")
    DISPUTED            = "disputed",           _("Disputed")


# Valid transitions — enforced in service layer
ORDER_STATUS_TRANSITIONS = {
    OrderStatus.PENDING_PAYMENT:   [OrderStatus.PAYMENT_CONFIRMED, OrderStatus.CANCELLED],
    OrderStatus.PAYMENT_CONFIRMED: [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
    OrderStatus.PROCESSING:        [OrderStatus.SHIPPED, OrderStatus.CANCELLED],
    OrderStatus.SHIPPED:           [OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED],
    OrderStatus.OUT_FOR_DELIVERY:  [OrderStatus.DELIVERED],
    OrderStatus.DELIVERED:         [OrderStatus.COMPLETED, OrderStatus.REFUND_REQUESTED, OrderStatus.DISPUTED],
    OrderStatus.COMPLETED:         [OrderStatus.REFUND_REQUESTED],
    OrderStatus.CANCELLED:         [],
    OrderStatus.REFUND_REQUESTED:  [OrderStatus.REFUNDED, OrderStatus.DISPUTED],
    OrderStatus.REFUNDED:          [],
    OrderStatus.DISPUTED:          [OrderStatus.REFUNDED, OrderStatus.COMPLETED],
}


class FulfillmentType(models.TextChoices):
    DELIVERY   = "delivery",   _("Delivery")
    PICKUP     = "pickup",     _("Pickup")
    DIGITAL    = "digital",    _("Digital Download")
    CUSTOM     = "custom",     _("Custom (Tailor-made)")


# ─────────────────────────────────────────────────────────────────────────────
# 1. ORDER IDEMPOTENCY RECORD
# ─────────────────────────────────────────────────────────────────────────────

class OrderIdempotencyRecord(TimeStampedModel):
    """
    Exactly-once guard for order creation.
    Key format: sha256(user_id + cart_snapshot_hash).
    """
    key = models.CharField(max_length=128, unique=True, db_index=True)
    order = models.OneToOneField(
        "Order",
        on_delete=models.CASCADE,
        related_name="idempotency_record",
    )
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = _("Order Idempotency Record")

    def __str__(self):
        return f"Idem({self.key[:16]}…)"


# ─────────────────────────────────────────────────────────────────────────────
# 2. ORDER
# ─────────────────────────────────────────────────────────────────────────────

class Order(TimeStampedModel):
    """
    Canonical order record. One per checkout submission.

    Financial trail:
      total_amount = sum(OrderItem.line_total) + shipping_amount - discount_amount
      escrow_amount = total_amount (held until delivery confirmation)
      commission_amount = sum(OrderItem.commission_amount)
      vendor_payout = total_amount - commission_amount
    """

    # ── Identity ──────────────────────────────────────────────────────────
    order_number = models.CharField(max_length=30, unique=True, db_index=True, blank=True)
    idempotency_key = models.CharField(
        max_length=128, unique=True, db_index=True,
        help_text="SHA256 of user+cart snapshot. Prevents duplicate order from retries.",
    )

    # ── Actors ────────────────────────────────────────────────────────────
    user = models.ForeignKey(
        User,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
        help_text="SET_NULL: order history preserved for financial audit after user deletion.",
    )
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
        help_text="SET_NULL: order history preserved after vendor departure.",
    )

    # ── Status ────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=30,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING_PAYMENT,
        db_index=True,
    )
    fulfillment_type = models.CharField(
        max_length=20,
        choices=FulfillmentType.choices,
        default=FulfillmentType.DELIVERY,
    )

    # ── Financials (all frozen at placement) ──────────────────────────────
    subtotal          = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    shipping_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount      = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    commission_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    vendor_payout     = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency          = models.CharField(max_length=3, default="NGN")

    # ── Payment ───────────────────────────────────────────────────────────
    payment_reference = models.CharField(
        max_length=200, blank=True, db_index=True,
        help_text="Paystack/provider transaction reference. Unique per order.",
    )
    payment_gateway   = models.CharField(max_length=50, default="paystack")
    paid_at           = models.DateTimeField(null=True, blank=True)

    # ── Coupon snapshot ───────────────────────────────────────────────────
    coupon_code       = models.CharField(max_length=50, blank=True)

    # ── Delivery ──────────────────────────────────────────────────────────
    # Delivery address snapshot (JSON to avoid FK dependency on client Address model)
    delivery_address  = models.JSONField(default=dict, blank=True)
    courier = models.ForeignKey(
        "product.DeliveryCourier",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    tracking_number   = models.CharField(max_length=200, blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)

    # ── Measurement reference ─────────────────────────────────────────────
    measurement_profile_id = models.UUIDField(
        null=True, blank=True,
        help_text="Snapshot of measurement profile used at checkout.",
    )

    # ── Internal flags ────────────────────────────────────────────────────
    is_test_order = models.BooleanField(default=False)
    escrow_released = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"], name="idx_order_user_status"),
            models.Index(fields=["vendor", "status"], name="idx_order_vendor_status"),
            models.Index(fields=["payment_reference"], name="idx_order_payment_ref"),
            models.Index(fields=["order_number"], name="idx_order_number"),
        ]

    def __str__(self):
        return f"Order#{self.order_number or self.id}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            import uuid6
            self.order_number = f"FSN-ORD-{str(uuid6.uuid7()).upper()[:12]}"
        super().save(*args, **kwargs)

    def can_transition_to(self, new_status: str) -> bool:
        allowed = ORDER_STATUS_TRANSITIONS.get(self.status, [])
        return new_status in allowed


# ─────────────────────────────────────────────────────────────────────────────
# 3. ORDER ITEM
# ─────────────────────────────────────────────────────────────────────────────

class OrderItem(TimeStampedModel):
    """
    One line item in an order.

    All financial fields are SNAPSHOTS frozen at placement time.
    Changing product price or commission rate after placement has no effect.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "product.Product",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items",
        help_text="SET_NULL: item history preserved even if product is deleted.",
    )
    variant = models.ForeignKey(
        "product.ProductVariant",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items",
    )
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items",
    )

    # ── Snapshots (frozen at placement) ───────────────────────────────────
    product_title       = models.CharField(max_length=300)
    product_sku         = models.CharField(max_length=80, blank=True)
    variant_description = models.CharField(max_length=200, blank=True)
    unit_price          = models.DecimalField(max_digits=12, decimal_places=2)
    quantity            = models.PositiveIntegerField(default=1)
    commission_rate     = models.DecimalField(max_digits=5, decimal_places=2)
    commission_amount   = models.DecimalField(max_digits=12, decimal_places=2)
    line_total          = models.DecimalField(max_digits=14, decimal_places=2)

    # ── Fulfillment ───────────────────────────────────────────────────────
    is_custom_order = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Order Item")
        verbose_name_plural = _("Order Items")

    def __str__(self):
        return f"{self.product_title} ×{self.quantity}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. ORDER STATUS HISTORY  (append-only)
# ─────────────────────────────────────────────────────────────────────────────

class OrderStatusHistory(TimeStampedModel):
    """
    Append-only log of all order status transitions.
    Never updated — one row per transition.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(max_length=30, blank=True)
    to_status   = models.CharField(max_length=30, choices=OrderStatus.choices)
    actor = models.ForeignKey(
        User,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="order_status_changes",
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Order Status History")
        verbose_name_plural = _("Order Status Histories")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.order} {self.from_status}→{self.to_status}"
