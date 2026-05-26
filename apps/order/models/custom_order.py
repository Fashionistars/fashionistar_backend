# apps/order/models/custom_order.py
"""
CustomOrder — Bespoke / Made-to-Measure order domain model.

Architecture:
  ─ CustomOrder: Client → Vendor commission request with design brief,
    optional product/order snapshot, and part-payment milestones.
  ─ CustomOrderMilestone: Represents one payment tranche (30/50/70/100 %)
    of an agreed bespoke order total.

Payment flow:
  1. Client submits CustomOrder (status=draft → submitted)
  2. Vendor reviews → approves with narration note + agreed amount
     (status=submitted → approved)
  3. System creates 4 milestones: 30 % → 50 % → 70 % → 100 %
  4. Client pays milestones sequentially; each payment triggers status
     transition on the milestone and unlocks the next.
  5. On final payment (100 %) → CustomOrder.status = in_production
  6. Vendor marks complete → status = completed

Reverse-relationship cheat-sheet:
  user.custom_orders_as_client  → CustomOrder rows (client side)
  user.custom_orders_as_vendor  → CustomOrder rows (vendor side)
  custom_order.milestones       → CustomOrderMilestone rows
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from django.db import models

from apps.common.models import SoftDeleteModel, TimeStampedModel

logger = logging.getLogger(__name__)


class CustomOrderStatus(models.TextChoices):
    DRAFT        = "draft",         "Draft"
    SUBMITTED    = "submitted",     "Submitted to Vendor"
    APPROVED     = "approved",      "Vendor Approved"
    IN_PRODUCTION= "in_production", "In Production"
    COMPLETED    = "completed",     "Completed"
    CANCELLED    = "cancelled",     "Cancelled"
    DISPUTED     = "disputed",      "Disputed"


class MilestonePaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PAID    = "paid",    "Paid"
    FAILED  = "failed",  "Failed"
    WAIVED  = "waived",  "Waived"


MILESTONE_PERCENTAGES = [30, 50, 70, 100]


class CustomOrder(TimeStampedModel, SoftDeleteModel):
    """
    A bespoke clothing commission from a client to a specific vendor.

    The client can attach a product snapshot (product_snapshot_id) or
    an existing order snapshot (order_snapshot_id) as a style reference.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Parties ────────────────────────────────────────────────────
    client = models.ForeignKey(
        "authentication.UnifiedUser",
        on_delete=models.PROTECT,
        related_name="custom_orders_as_client",
        limit_choices_to={"role": "client"},
        help_text="The client who initiated the commission.",
    )
    vendor = models.ForeignKey(
        "authentication.UnifiedUser",
        on_delete=models.PROTECT,
        related_name="custom_orders_as_vendor",
        limit_choices_to={"role": "vendor"},
        help_text="The vendor fulfilling the commission.",
    )

    # ── Reference ──────────────────────────────────────────────────
    reference = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        help_text="Human-readable reference e.g. CO-20260526-0001",
    )

    # ── Status ─────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=CustomOrderStatus.choices,
        default=CustomOrderStatus.DRAFT,
        db_index=True,
    )

    # ── Design Brief ───────────────────────────────────────────────
    design_brief = models.TextField(
        help_text="Detailed description of the client's custom design requirements.",
    )
    reference_images = models.JSONField(
        default=list,
        blank=True,
        help_text="List of uploaded image URLs for style reference.",
    )

    # ── Snapshot References (optional) ────────────────────────────
    product_snapshot_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Product PID used as style reference.",
    )
    order_snapshot_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Existing order_number used as style reference.",
    )

    # ── Financial ─────────────────────────────────────────────────
    budget_ngn = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Client's proposed budget in NGN.",
    )
    agreed_amount_ngn = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Agreed total set by vendor on approval.",
    )

    # ── Vendor Narration ──────────────────────────────────────────
    vendor_approval_note = models.TextField(
        blank=True,
        default="",
        help_text="Vendor's note when approving/declining the design brief.",
    )

    class Meta:
        verbose_name = "Custom Order"
        verbose_name_plural = "Custom Orders"
        db_table = "custom_order"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "status"], name="co_client_status_idx"),
            models.Index(fields=["vendor", "status"], name="co_vendor_status_idx"),
            models.Index(fields=["reference"],         name="co_reference_idx"),
        ]

    def __str__(self) -> str:
        return f"CustomOrder({self.reference} | {self.status})"

    def save(self, *args, **kwargs) -> None:
        if not self.reference:
            self.reference = self._generate_reference()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference() -> str:
        from django.utils import timezone
        today = timezone.now().strftime("%Y%m%d")
        short = str(uuid.uuid4())[:6].upper()
        return f"CO-{today}-{short}"

    # ── Business Logic Helpers ────────────────────────────────────

    def create_milestones(self) -> list["CustomOrderMilestone"]:
        """
        Create the 4 milestone payment tranches once vendor approves.
        Called by the approve service after setting agreed_amount_ngn.
        """
        if not self.agreed_amount_ngn:
            raise ValueError("agreed_amount_ngn must be set before creating milestones.")
        total = self.agreed_amount_ngn
        milestones = []
        for pct in MILESTONE_PERCENTAGES:
            amount = (total * Decimal(pct) / Decimal(100)).quantize(Decimal("0.01"))
            m = CustomOrderMilestone(
                custom_order=self,
                milestone_pct=pct,
                amount_ngn=amount,
            )
            milestones.append(m)
        CustomOrderMilestone.objects.bulk_create(milestones)
        return milestones

    @property
    def paid_pct(self) -> int:
        """Sum of paid milestone percentages."""
        paid = self.milestones.filter(payment_status=MilestonePaymentStatus.PAID)
        return sum(m.milestone_pct for m in paid)

    @property
    def next_milestone(self) -> "CustomOrderMilestone | None":
        """Return the lowest pending milestone, or None if all paid."""
        return (
            self.milestones
            .filter(payment_status=MilestonePaymentStatus.PENDING)
            .order_by("milestone_pct")
            .first()
        )


class CustomOrderMilestone(TimeStampedModel):
    """
    One payment tranche for a CustomOrder.

    Milestone percentages are: 30, 50, 70, 100.
    Each must be paid in sequence before the next is unlocked.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    custom_order = models.ForeignKey(
        CustomOrder,
        on_delete=models.CASCADE,
        related_name="milestones",
    )
    milestone_pct = models.PositiveSmallIntegerField(
        help_text="Percentage of total order this milestone covers: 30, 50, 70, or 100.",
    )
    amount_ngn = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="NGN amount for this tranche.",
    )
    payment_status = models.CharField(
        max_length=10,
        choices=MilestonePaymentStatus.choices,
        default=MilestonePaymentStatus.PENDING,
        db_index=True,
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="External payment provider reference.",
    )

    class Meta:
        verbose_name = "Custom Order Milestone"
        verbose_name_plural = "Custom Order Milestones"
        db_table = "custom_order_milestone"
        unique_together = [("custom_order", "milestone_pct")]
        ordering = ["milestone_pct"]

    def __str__(self) -> str:
        return (
            f"Milestone {self.milestone_pct}% — {self.custom_order.reference}"
            f" [{self.payment_status}]"
        )
