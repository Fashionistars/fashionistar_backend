# apps/order/models/discount_code.py
"""
DiscountCode — platform-wide or vendor-scoped promotional discount entity.

Architecture Rules:
  - SoftDeleteModel + TimeStampedModel (deactivating soft-deletes the code).
  - Idempotency: CartService validates and applies via select_for_update() + atomic.
  - All financial computation (discount_value, max_discount) uses Decimal.
  - Usage tracking: current_uses vs max_uses enforced atomically.
  - Vendor-scoped codes: vendor FK set; platform codes: vendor=None.
  - Minimum order value enforced in CartService, not here.

Discount types:
  PERCENTAGE  — e.g. 15% off order subtotal
  FIXED       — e.g. ₦500 off order subtotal
  FREE_SHIP   — waive shipping fee
  BOGO        — buy one get one (CartService interprets this)
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteModel, TimeStampedModel


class DiscountCode(TimeStampedModel, SoftDeleteModel):
    """
    Promotional discount code entity.

    Applied to a Cart via CartService. Validates:
      - Code exists and is_active.
      - Cart subtotal >= minimum_order_value.
      - current_uses < max_uses (atomically, with select_for_update).
      - valid_from <= now <= valid_until.
      - vendor scope: code.vendor is None OR code.vendor == cart.vendor.

    Attributes:
        code: Unique, case-insensitive coupon code string (e.g. "FASHION20").
        vendor: Owning vendor for scoped codes. Null = platform-wide.
        created_by: Staff user who created the discount.
        discount_type: Type of discount applied.
        discount_value: Amount / percentage of the discount.
        max_discount_amount: Cap on percentage discount value (in NGN).
        minimum_order_value: Minimum cart subtotal to qualify.
        valid_from: Discount starts being valid at this time.
        valid_until: Discount expires at this time.
        max_uses: Global usage cap (0 = unlimited).
        max_uses_per_user: Per-user cap (0 = unlimited).
        current_uses: Atomically incremented counter.
        is_active: Admin toggle. Soft-delete also disables.
        is_first_order_only: Restrict to first-time buyers only.
        description: Admin note about the campaign.
        metadata: Arbitrary JSON for UTM params, campaign IDs, etc.
    """

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", _("Percentage Off")
        FIXED = "fixed", _("Fixed Amount Off")
        FREE_SHIPPING = "free_shipping", _("Free Shipping")
        BOGO = "bogo", _("Buy One Get One Free")

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_("Code"),
        help_text=_("Case-insensitive coupon code, e.g. FASHION20."),
    )
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="discount_codes",
        verbose_name=_("Vendor"),
        help_text=_("Null = platform-wide discount."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_discount_codes",
        verbose_name=_("Created By"),
    )
    discount_type = models.CharField(
        max_length=15,
        choices=DiscountType.choices,
        db_index=True,
        verbose_name=_("Discount Type"),
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("Discount Value"),
        help_text=_("% value for PERCENTAGE type, NGN amount for FIXED type."),
    )
    max_discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name=_("Max Discount Amount (NGN)"),
        help_text=_("Cap on percentage discounts in NGN. Leave blank for no cap."),
    )
    minimum_order_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Minimum Order Value (NGN)"),
    )
    valid_from = models.DateTimeField(
        verbose_name=_("Valid From"),
        db_index=True,
    )
    valid_until = models.DateTimeField(
        verbose_name=_("Valid Until"),
        db_index=True,
    )
    max_uses = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Max Total Uses"),
        help_text=_("0 = unlimited."),
    )
    max_uses_per_user = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Max Uses Per User"),
        help_text=_("0 = unlimited."),
    )
    current_uses = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Current Total Uses"),
        help_text=_("Atomically incremented on each redemption."),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("Active"),
    )
    is_first_order_only = models.BooleanField(
        default=False,
        verbose_name=_("First Order Only"),
        help_text=_("Restrict this code to clients with no previous orders."),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Admin/internal note about this campaign."),
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Metadata"),
        help_text=_("UTM params, campaign IDs, or A/B test labels."),
    )

    class Meta:
        verbose_name = _("Discount Code")
        verbose_name_plural = _("Discount Codes")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["code"], name="dc_code_idx"),
            models.Index(fields=["is_active", "valid_from", "valid_until"], name="dc_active_validity_idx"),
            models.Index(fields=["vendor", "is_active"], name="dc_vendor_active_idx"),
        ]

    def __str__(self) -> str:
        vendor_label = f" ({self.vendor})" if self.vendor_id else " [Platform]"
        return f"{self.code}{vendor_label} — {self.get_discount_type_display()}"

    def save(self, *args, **kwargs) -> None:
        """Normalize code to uppercase for case-insensitive matching."""
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def is_exhausted(self) -> bool:
        """True if max_uses limit has been reached."""
        return bool(self.max_uses and self.current_uses >= self.max_uses)

    @property
    def is_currently_valid(self) -> bool:
        """True if the code is active and within its validity window."""
        from django.utils import timezone
        now = timezone.now()
        return self.is_active and self.valid_from <= now <= self.valid_until and not self.is_exhausted
