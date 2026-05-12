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
from cloudinary.models import CloudinaryField

User = get_user_model()
logger = logging.getLogger(__name__)

import shortuuid
import uuid

STATUS = (
    ("draft", "Draft"),
    ("disabled", "Disabled"),
    ("rejected", "Rejected"),
    ("in_review", "In Review"),
    ("published", "Published"),
)


PAYMENT_STATUS = (
    ("paid", "Paid"),
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("cancelled", "Cancelled"),
    ("initiated", "Initiated"),
    ("failed", "failed"),
    ("refunding", "refunding"),
    ("refunded", "refunded"),
    ("unpaid", "unpaid"),
    ("expired", "expired"),
)


ORDER_STATUS = (
    ("Pending", "Pending"),
    ("Fulfilled", "Fulfilled"),
    ("Partially Fulfilled", "Partially Fulfilled"),
    ("Cancelled", "Cancelled"),
)


OFFER_STATUS = (
    ("accepted", "Accepted"),
    ("rejected", "Rejected"),
    ("pending", "Pending"),
)


PRODUCT_CONDITION_RATING = (
    (1, "1/10"),
    (2, "2/10"),
    (3, "3/10"),
    (4, "4/10"),
    (5, "5/10"),
    (6, "6/10"),
    (7, "7/10"),
    (8, "8/10"),
    (9, "9/10"),
    (10, "10/10"),
)


DELIVERY_STATUS = (
    ("On Hold", "On Hold"),
    ("Shipping Processing", "Shipping Processing"),
    ("Shipped", "Shipped"),
    ("Arrived", "Arrived"),
    ("Returning", "Returning"),
    ("Returned", "Returned"),
    ("Awaiting Pickup", "Awaiting Pickup"),
    ("In Transit", "In Transit"),
    ("Delivered", "Delivered"),
)


RATING = (
    (1, "★☆☆☆☆"),
    (2, "★★☆☆☆"),
    (3, "★★★☆☆"),
    (4, "★★★★☆"),
    (5, "★★★★★"),
)


# ─────────────────────────────────────────────────────────────────────────────
# STATUS CHOICES
# ─────────────────────────────────────────────────────────────────────────────


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", _("Pending Payment")
    PAYMENT_CONFIRMED = "payment_confirmed", _("Payment Confirmed")
    PROCESSING = "processing", _("Processing")
    SHIPPED = "shipped", _("Shipped")
    OUT_FOR_DELIVERY = "out_for_delivery", _("Out for Delivery")
    DELIVERED = "delivered", _("Delivered")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")
    REFUND_REQUESTED = "refund_requested", _("Refund Requested")
    REFUNDED = "refunded", _("Refunded")
    DISPUTED = "disputed", _("Disputed")


# Valid transitions — enforced in service layer
ORDER_STATUS_TRANSITIONS = {
    OrderStatus.PENDING_PAYMENT: [OrderStatus.PAYMENT_CONFIRMED, OrderStatus.CANCELLED],
    OrderStatus.PAYMENT_CONFIRMED: [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
    OrderStatus.PROCESSING: [OrderStatus.SHIPPED, OrderStatus.CANCELLED],
    OrderStatus.SHIPPED: [OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED],
    OrderStatus.OUT_FOR_DELIVERY: [OrderStatus.DELIVERED],
    OrderStatus.DELIVERED: [
        OrderStatus.COMPLETED,
        OrderStatus.REFUND_REQUESTED,
        OrderStatus.DISPUTED,
    ],
    OrderStatus.COMPLETED: [OrderStatus.REFUND_REQUESTED],
    OrderStatus.CANCELLED: [],
    OrderStatus.REFUND_REQUESTED: [OrderStatus.REFUNDED, OrderStatus.DISPUTED],
    OrderStatus.REFUNDED: [],
    OrderStatus.DISPUTED: [OrderStatus.REFUNDED, OrderStatus.COMPLETED],
}


class FulfillmentType(models.TextChoices):
    DELIVERY = "delivery", _("Delivery")
    PICKUP = "pickup", _("Pickup")
    DIGITAL = "digital", _("Digital Download")
    CUSTOM = "custom", _("Custom (Tailor-made)")


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
        related_name="order_idempotency_record",
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
    order_number = models.CharField(
        max_length=30, unique=True, db_index=True, blank=True
    )

    idempotency_key = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="SHA256 of user+cart snapshot. Prevents duplicate order from retries.",
    )

    # ── Actors ────────────────────────────────────────────────────────────
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="user_orders",
        help_text="SET_NULL: order history preserved for financial audit after user deletion.",
    )
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vendor_orders",
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
    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    shipping_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    commission_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    vendor_payout = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="NGN")

    # ── Payment ───────────────────────────────────────────────────────────
    payment_reference = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
        help_text="Paystack/provider transaction reference. Unique per order.",
    )
    payment_gateway = models.CharField(max_length=50, default="paystack")
    paid_at = models.DateTimeField(null=True, blank=True)

    # ── Coupon snapshot ───────────────────────────────────────────────────
    coupon_code = models.CharField(max_length=50, blank=True)

    # ── Delivery ──────────────────────────────────────────────────────────
    # Delivery address snapshot (JSON to avoid FK dependency on client Address model)
    delivery_address = models.JSONField(default=dict, blank=True)
    delivery_courier = models.ForeignKey(
        "product.DeliveryCourier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="delivery_courier_orders",
    )
    tracking_number = models.CharField(max_length=200, blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)

    # ── Measurement reference ─────────────────────────────────────────────
    measurement_profile_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Snapshot of measurement profile used at checkout.",
    )
    is_custom_order = models.BooleanField(
        default=False,
        help_text="True if this is a fully custom-made item (not pre-made).",
    )

    measurement_data = models.JSONField(
        blank=True,
        default=dict,
        help_text="Snapshot of customer measurements (height, weight, bust, etc.)",
    )

    customization_notes = models.TextField(
        blank=True,
        help_text="Any special notes from the customer about the custom order.",
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

    @classmethod
    def revenue_statuses(cls) -> list[str]:
        """Statuses that represent value held, earned, or released."""
        return [
            OrderStatus.PAYMENT_CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.DELIVERED,
            OrderStatus.COMPLETED,
        ]

    @classmethod
    def get_status_counts_for_user(cls, user_id) -> dict[str, int]:
        """Group a client's orders by status through the user_orders relation."""
        from django.db.models import Count

        rows = (
            cls.objects.filter(user_id=user_id)
            .values("status")
            .annotate(count=Count("id"))
        )
        return {row["status"]: row["count"] for row in rows}

    @classmethod
    async def aget_status_counts_for_user(cls, user_id) -> dict[str, int]:
        """Async variant of get_status_counts_for_user."""
        from django.db.models import Count

        rows = (
            cls.objects.filter(user_id=user_id)
            .values("status")
            .annotate(count=Count("id"))
        )
        return {row["status"]: row["count"] async for row in rows}

    @classmethod
    def get_status_counts_for_vendor(cls, vendor_id) -> dict[str, int]:
        """Group a vendor's orders by status through vendor_orders."""
        from django.db.models import Count

        rows = (
            cls.objects.filter(vendor_id=vendor_id)
            .values("status")
            .annotate(count=Count("id"))
        )
        return {row["status"]: row["count"] for row in rows}

    @classmethod
    async def aget_status_counts_for_vendor(cls, vendor_id) -> dict[str, int]:
        """Async variant of get_status_counts_for_vendor."""
        from django.db.models import Count

        rows = (
            cls.objects.filter(vendor_id=vendor_id)
            .values("status")
            .annotate(count=Count("id"))
        )
        return {row["status"]: row["count"] async for row in rows}

    @classmethod
    def get_financial_summary_for_vendor(cls, vendor_id) -> dict:
        """Single-query vendor order financial aggregate for DRF/admin reads."""
        from django.db.models import Count, Sum

        result = (
            cls.objects.filter(vendor_id=vendor_id, status__in=cls.revenue_statuses())
            .aggregate(
                total_revenue=Sum("total_amount"),
                total_commission=Sum("commission_amount"),
                total_payout=Sum("vendor_payout"),
                order_count=Count("id"),
            )
        )
        return {
            "total_revenue": result["total_revenue"] or Decimal("0.00"),
            "total_commission": result["total_commission"] or Decimal("0.00"),
            "total_payout": result["total_payout"] or Decimal("0.00"),
            "order_count": result["order_count"] or 0,
        }

    @classmethod
    async def aget_financial_summary_for_vendor(cls, vendor_id) -> dict:
        """Async single-query vendor order financial aggregate."""
        from django.db.models import Count, Sum

        result = await (
            cls.objects.filter(vendor_id=vendor_id, status__in=cls.revenue_statuses())
            .aaggregate(
                total_revenue=Sum("total_amount"),
                total_commission=Sum("commission_amount"),
                total_payout=Sum("vendor_payout"),
                order_count=Count("id"),
            )
        )
        return {
            "total_revenue": result["total_revenue"] or Decimal("0.00"),
            "total_commission": result["total_commission"] or Decimal("0.00"),
            "total_payout": result["total_payout"] or Decimal("0.00"),
            "order_count": result["order_count"] or 0,
        }

    def get_snapshot_totals_from_db(self) -> dict:
        """Aggregate immutable CartOrderItem snapshots through the reverse FK."""
        from django.db.models import Count, Sum

        result = self.cart_order_items.aggregate(
            item_count=Count("id"),
            quantity=Sum("quantity"),
            line_total=Sum("line_total"),
            commission_amount=Sum("commission_amount"),
            vendor_payout=Sum("vendor_payout"),
        )
        return {
            "item_count": result["item_count"] or 0,
            "quantity": result["quantity"] or 0,
            "line_total": result["line_total"] or Decimal("0.00"),
            "commission_amount": result["commission_amount"] or Decimal("0.00"),
            "vendor_payout": result["vendor_payout"] or Decimal("0.00"),
        }

    async def aget_snapshot_totals_from_db(self) -> dict:
        """Async aggregate for immutable CartOrderItem snapshots."""
        from django.db.models import Count, Sum

        result = await self.cart_order_items.aaggregate(
            item_count=Count("id"),
            quantity=Sum("quantity"),
            line_total=Sum("line_total"),
            commission_amount=Sum("commission_amount"),
            vendor_payout=Sum("vendor_payout"),
        )
        return {
            "item_count": result["item_count"] or 0,
            "quantity": result["quantity"] or 0,
            "line_total": result["line_total"] or Decimal("0.00"),
            "commission_amount": result["commission_amount"] or Decimal("0.00"),
            "vendor_payout": result["vendor_payout"] or Decimal("0.00"),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3. CART ORDER ITEM  (immutable cart snapshot per order placement)
# ────────────────────────────────────────────────────────────────────────────


class CartOrderItem(TimeStampedModel):
    """
    Immutable snapshot of a CartItem captured at the moment an Order is placed.

    Purpose
    -------
    Preserves the full cart-level context even if:
      - The Cart is cleared after checkout.
      - The Product or ProductVariant is later soft-deleted.
      - Prices change after the order is placed.

    Population
    ----------
    Created in bulk by the order.placed event handler (apps.common.events),
    NOT via Django signals.  This keeps the Order service decoupled from the
    Cart domain.

    on_delete policy
    ----------------
    - CartOrderItem → Order: CASCADE  (audit record tied to order lifecycle)
    - CartOrderItem → Product: SET_NULL  (product history preserved)
    - CartOrderItem → ProductVariant: SET_NULL  (variant history preserved)
    """

    # ── Order link ────────────────────────────────────────────────────────
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="cart_order_items",
        help_text="Parent order. CASCADE: snapshot deleted with order if hard-deleted.",
    )

    # ── Product references (nullable for future-proofing) ─────────────────
    product = models.ForeignKey(
        "product.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cart_order_product_snapshots",
        help_text="SET_NULL: snapshot preserved if product is deleted.",
    )
    variant = models.ForeignKey(
        "product.ProductVariant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cart_order_variant_snapshots",
        help_text="SET_NULL: snapshot preserved if variant is deleted.",
    )
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cart_order_vendor_snapshots",
        help_text="SET_NULL: snapshot preserved if vendor is deleted.",
    )
    # ── Identity snapshots (frozen at placement) ──────────────────────────
    product_sku_snapshot = models.CharField(
        max_length=80,
        blank=True,
        help_text="Product SKU at time of order. Preserved for returns/exchanges.",
    )
    product_title_snapshot = models.CharField(
        max_length=300,
        help_text="Product title at time of order.",
    )
    variant_description_snapshot = models.CharField(
        max_length=200,
        blank=True,
        help_text="Variant label (e.g. 'Red / XL') at time of order.",
    )
    vendor_name_snapshot = models.CharField(
        max_length=200,
        blank=True,
        help_text="Vendor name at time of order.",
    )
    cover_image_snapshot = CloudinaryField(
        "cover_image_snapshot",
        blank=True,
        help_text="Cloudinary URL of product cover image at order time.",
    )
    variant_images_snapshot = CloudinaryField(
        "variant_images_snapshot",
        blank=True,
        help_text="Cloudinary URL of product variant images at order time.",
    )

    # ── Financial snapshots ───────────────────────────────────────────────
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Unit price snapshot from CartItem at checkout.",
    )
    quantity = models.PositiveIntegerField(
        help_text="Quantity ordered.",
    )
    line_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="unit_price × quantity, frozen at placement.",
    )
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        help_text="Platform commission % at time of order. Used for vendor payout calc.",
    )
    commission_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="commission_rate / 100 × line_total, frozen at placement.",
    )
    vendor_payout = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="line_total - commission_amount, frozen at placement.",
    )

    # ── Fulfillment ───────────────────────────────────────────────────────
    is_custom_order = models.BooleanField(
        default=False,
        help_text="True if this is a fully custom-made item (not pre-made).",
    )

    measurement_data = models.JSONField(
        blank=True,
        default=dict,
        help_text="Snapshot of customer measurements (height, weight, bust, etc.)",
    )

    customization_notes = models.TextField(
        blank=True,
        help_text="Any special notes from the customer about the custom order.",
    )

    # ── Attribute snapshots (for order summary / return flow) ─────────────
    size_snapshot = models.CharField(max_length=80, blank=True)
    color_snapshot = models.CharField(max_length=80, blank=True)

    # ── Source reference ──────────────────────────────────────────────────
    cart_item_idempotency_key = models.UUIDField(
        null=True,
        blank=True,
        help_text="Original CartItem.idempotency_key. Enables dedup on retry.",
    )

    class Meta:
        verbose_name = _("Cart Order Item")
        verbose_name_plural = _("Cart Order Items")
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["order", "product"],
                name="idx_cart_order_item_order_prod",
            ),
        ]

    def __str__(self):
        return (
            f"{self.product_title_snapshot} ×{self.quantity} (Order#{self.order.order_number})"
        )

    def save(self, *args, **kwargs):
        """Auto-compute commission_amount and vendor_payout before saving."""
        if self.unit_price is not None and self.quantity is not None:
            self.line_total = self.unit_price * self.quantity
        if self.line_total is not None and self.commission_rate is not None:
            self.commission_amount = (self.commission_rate / 100) * self.line_total
            self.vendor_payout = self.line_total - self.commission_amount
        super().save(*args, **kwargs)


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
        related_name="order_status_history",
    )
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30, choices=OrderStatus.choices)
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_status_history_actor",
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Order Status History")
        verbose_name_plural = _("Order Status Histories")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.order} {self.from_status}→{self.to_status}"
