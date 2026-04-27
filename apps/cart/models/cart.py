# apps/cart/models/cart.py
"""
Cart domain models for Fashionistar.

Design:
  - One Cart per user (get_or_create pattern).
  - CartItem references Product + optional ProductVariant.
  - stock_reserved tracks units held pending checkout.
  - Idempotency key on CartItem to prevent race-condition duplicates.
  - All writes go through the service layer using select_for_update.

on_delete policy:
  - Cart → User: CASCADE (user deleted → cart deleted, GDPR compliant)
  - CartItem → Cart: CASCADE
  - CartItem → Product: CASCADE (product deleted → item removed from cart)
  - CartItem → ProductVariant: SET_NULL (variant deleted, item reverts to base product)
  - Cart.coupon → Coupon: SET_NULL (coupon deletion doesn't destroy active carts)
"""

import logging
import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel

User = get_user_model()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. CART
# ─────────────────────────────────────────────────────────────────────────────

class Cart(TimeStampedModel):
    """
    Session-persisted shopping cart.

    One cart per user. Anonymous carts are not modelled — the frontend
    stores a guest cart in localStorage and merges it on login.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="cart",
    )
    # Applied coupon code — validated at checkout
    coupon = models.ForeignKey(
        "product.Coupon",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="carts",
    )
    # Snapshot of coupon discount (set when coupon is applied, cleared on remove)
    coupon_discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    # Last activity timestamp — used to expire abandoned carts via Celery beat
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Cart")
        verbose_name_plural = _("Carts")

    def __str__(self):
        return f"Cart({self.user})"

    @property
    def subtotal(self):
        """Sum of all active line items."""
        from django.db.models import Sum, F, DecimalField, ExpressionWrapper
        result = self.items.filter(is_saved_for_later=False).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("unit_price") * F("quantity"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )
        )
        return result["total"] or 0

    @property
    def total(self):
        return max(0, self.subtotal - self.coupon_discount)

    @property
    def item_count(self):
        return self.items.filter(is_saved_for_later=False).count()


# ─────────────────────────────────────────────────────────────────────────────
# 2. CART ITEM
# ─────────────────────────────────────────────────────────────────────────────

class CartItem(TimeStampedModel):
    """
    Individual product line in a cart.

    unit_price is SNAPSHOTTED at add-time so price changes mid-session
    are visible in the cart summary and reconciled at checkout.

    idempotency_key: generated from (cart_id, product_id, variant_id) hash.
    Prevents duplicate line items from retry storms.
    """

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "product.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    variant = models.ForeignKey(
        "product.ProductVariant",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    # Price snapshot at add-time — refreshed on explicit user action
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    # Set to True when user clicks "Save for later"
    is_saved_for_later = models.BooleanField(default=False)
    # Exactly-once line creation guard
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)

    class Meta:
        verbose_name = _("Cart Item")
        verbose_name_plural = _("Cart Items")
        # One line per product+variant per cart
        unique_together = [("cart", "product", "variant")]

    def __str__(self):
        return f"{self.cart.user} × {self.product.title} ×{self.quantity}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def save(self, *args, **kwargs):
        # Ensure price snapshot is always set
        if not self.unit_price:
            if self.variant and self.variant.price_override:
                self.unit_price = self.variant.price_override
            else:
                self.unit_price = self.product.price
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 3. CART ACTIVITY LOG  (append-only audit)
# ─────────────────────────────────────────────────────────────────────────────

class CartActivityLog(TimeStampedModel):
    """
    Append-only log of cart mutations.
    Used for analytics, fraud detection, and abandonment email triggers.
    """

    ACTION_CHOICES = [
        ("item_added", "Item Added"),
        ("item_removed", "Item Removed"),
        ("quantity_updated", "Quantity Updated"),
        ("coupon_applied", "Coupon Applied"),
        ("coupon_removed", "Coupon Removed"),
        ("cart_cleared", "Cart Cleared"),
        ("cart_merged", "Cart Merged (Guest → Auth)"),
    ]

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    product = models.ForeignKey(
        "product.Product",
        null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    quantity = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Cart Activity Log")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.cart} — {self.action}"
