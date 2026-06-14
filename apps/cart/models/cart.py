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
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteModel, TimeStampedModel

User = get_user_model()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. CART
# ─────────────────────────────────────────────────────────────────────────────


class Cart(TimeStampedModel, SoftDeleteModel):
    """
    Session-persisted shopping cart.

    Supports both authenticated and anonymous users:
      - Authenticated: linked via user (OneToOneField, nullable).
      - Anonymous:     linked via session_key (from localStorage/cookie).

    Exactly ONE of user or session_key must be set — enforced in clean().
    On login, call Cart.merge_from(session_key, user) to promote the
    anonymous cart to an authenticated cart atomically.
    """

    user = models.OneToOneField(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="user_cart",
        help_text="Set for authenticated users. NULL for anonymous carts.",
    )
    # 40-char key matching Django session key / uuid4 hex from localStorage
    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Set for anonymous users. Must be NULL when user is set.",
    )
    # Applied coupon code — validated at checkout
    coupon = models.ForeignKey(
        "product.Coupon",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="carts_with_coupons",
    )
    # Snapshot of coupon discount (set when coupon is applied, cleared on remove)
    coupon_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Last activity timestamp — used to expire abandoned carts via Celery beat
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Cart")
        verbose_name_plural = _("Carts")
        constraints = [
            # Enforce: at least one of user or session_key must be set
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False) | models.Q(session_key__isnull=False)
                ),
                name="cart_must_have_user_or_session_key",
            ),
            # Enforce: a cart belongs to exactly one owner path.
            models.CheckConstraint(
                condition=~(
                    models.Q(user__isnull=False) & models.Q(session_key__isnull=False)
                ),
                name="cart_user_session_key_mutually_exclusive",
            ),
        ]

    def clean(self):
        """Ensure exactly one of user or session_key is set."""
        if self.user_id is None and not self.session_key:
            raise ValidationError(
                _("A cart must be linked to either a user or a session_key.")
            )
        if self.user_id is not None and self.session_key:
            raise ValidationError(
                _("A cart cannot have both user and session_key set simultaneously.")
            )

    def __str__(self):
        if self.user_id:
            return f"Cart(user={self.user})"
        return f"Cart(session={self.session_key})"

    @classmethod
    def merge_from(cls, session_key: str, user) -> "Cart":
        """
        Merge an anonymous session cart into a user's authenticated cart.

        Strategy:
          1. Locate the anonymous cart by session_key.
          2. Get-or-create the user's cart.
          3. For each anonymous CartItem:
             - If an identical (product, variant) line already exists in
               the user cart → increment quantity.
             - Otherwise → move the item to the user cart.
          4. Log a CartActivityLog entry with action='cart_merged'.
          5. Delete the anonymous cart.

        All steps run inside transaction.atomic().
        Returns the user's cart.
        """
        with transaction.atomic():
            try:
                anon_cart = cls.objects.select_for_update().get(
                    session_key=session_key, user__isnull=True
                )
            except cls.DoesNotExist:
                # No anonymous cart — just get-or-create the user cart.
                user_cart, _ = cls.objects.get_or_create(
                    user=user, defaults={"session_key": None}
                )
                return user_cart

            user_cart, _ = cls.objects.select_for_update().get_or_create(
                user=user, defaults={"session_key": None}
            )

            for anon_item in anon_cart.items.select_for_update().all():
                existing = user_cart.items.filter(
                    product_id=anon_item.product_id,
                    variant_id=anon_item.variant_id,
                ).first()
                if existing:
                    existing.quantity += anon_item.quantity
                    existing.save(update_fields=["quantity", "updated_at"])
                else:
                    anon_item.cart = user_cart
                    anon_item.save(update_fields=["cart", "updated_at"])

            CartActivityLog.objects.create(
                cart=user_cart,
                action="cart_merged",
                metadata={"merged_from_session": session_key},
            )

            anon_cart.delete()
            logger.info(
                "Cart merge: session_key=%s → user=%s",
                session_key,
                user.pk,
            )
            return user_cart

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

    def get_summary_from_db(self) -> dict:
        """
        Return a cart summary computed through the Cart -> items reverse join.

        This keeps subtotal and item-count math at the database layer instead
        of recomputing rows inside serializers or API views.
        """
        from decimal import Decimal
        from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum

        aggregate = self.items.filter(is_saved_for_later=False).aggregate(
            item_count=Count("id"),
            subtotal=Sum(
                ExpressionWrapper(
                    F("unit_price") * F("quantity"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
        )
        subtotal = aggregate["subtotal"] or Decimal("0.00")
        discount = self.coupon_discount or Decimal("0.00")
        total = max(Decimal("0.00"), subtotal - discount)
        return {
            "item_count": aggregate["item_count"] or 0,
            "subtotal": subtotal,
            "coupon_discount": discount,
            "total": total,
            "currency": "NGN",
            "coupon_code": self.coupon.code if self.coupon_id else None,
        }

    async def aget_summary_from_db(self) -> dict:
        """
        Async variant of get_summary_from_db using native async ORM terminals.

        Query builders such as filter() are intentionally sync-looking because
        Django does not evaluate them until aaggregate() / afirst() is awaited.
        """
        from decimal import Decimal

        # pyrefly: ignore [missing-import]
        from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum

        aggregate = await self.items.filter(is_saved_for_later=False).aaggregate(
            item_count=Count("id"),
            subtotal=Sum(
                ExpressionWrapper(
                    F("unit_price") * F("quantity"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
        )
        coupon_row = await (
            type(self)
            .objects.filter(pk=self.pk)
            .values("coupon_discount", "coupon__code")
            .afirst()
        )
        subtotal = aggregate["subtotal"] or Decimal("0.00")
        discount = (coupon_row or {}).get("coupon_discount") or Decimal("0.00")
        total = max(Decimal("0.00"), subtotal - discount)
        return {
            "item_count": aggregate["item_count"] or 0,
            "subtotal": subtotal,
            "coupon_discount": discount,
            "total": total,
            "currency": "NGN",
            "coupon_code": (coupon_row or {}).get("coupon__code"),
        }

    async def aget_item_count_from_db(self) -> int:
        """Return active cart line count using the cart.items reverse join."""
        return await self.items.filter(is_saved_for_later=False).acount()

    async def alist_saved_for_later_from_db(self) -> list[dict]:
        """Return saved-for-later rows through the Cart -> items relation."""
        rows = self.items.filter(is_saved_for_later=True).values(
            "id",
            "product__id",
            "product__title",
            "product__slug",
            "unit_price",
            "quantity",
            "variant__id",
            "variant__size__size_label",
            "variant__color_name",
        )
        return [row async for row in rows]

    async def alist_activity_from_db(self, *, limit: int = 20) -> list[dict]:
        """Return append-only cart activity rows through activity_logs."""
        rows = self.activity_logs.order_by("-created_at").values(
            "id",
            "action",
            "product__title",
            "quantity",
            "metadata",
            "created_at",
        )[:limit]
        return [row async for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# 2. CART ITEM
# ─────────────────────────────────────────────────────────────────────────────


class CartItem(TimeStampedModel, SoftDeleteModel):
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
        "product.ProductVariantGalleryMedia",
        null=True,
        blank=True,
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
        actor = self.cart.user or f"anon:{self.cart.session_key}"
        return f"{actor} × {self.product.title} ×{self.quantity}"

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
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cart_activity_logs",
    )
    quantity = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Cart Activity Log")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.cart} — {self.action}"
