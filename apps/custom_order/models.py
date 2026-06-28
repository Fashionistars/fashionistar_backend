# apps/custom_order/models.py
"""
FASHIONISTAR — Custom Order (Bespoke Commission) Domain.

Architecture:
  CustomOrder   — the top-level commission contract between a client and a vendor.
  CustomOrderMilestone — payment tranche rows (30/50/70/100%) linked to the order.

Design decisions:
  • Milestones are auto-seeded when a vendor approves the order (see service layer).
  • `budget_ngn`   = client's stated budget (stored even if vendor negotiates).
  • `agreed_amount_ngn` = final price agreed by vendor after approval (nullable until approval).
  • Reference images are stored as a JSON list of Cloudinary secure URLs.
  • Status machine: Draft → Submitted → Approved → In Production → Completed.

Indices optimised for the two most common query patterns:
  • Client lists their own orders by status.
  • Vendor lists incoming orders by status.

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

import uuid
import logging
from decimal import Decimal

from django.db import models
from django.utils import timezone

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
    PENDING  = "pending",  "Pending"
    PAID     = "paid",     "Paid"
    FAILED   = "failed",   "Failed"
    WAIVED   = "waived",   "Waived"


MILESTONE_PERCENTAGES = [30, 50, 70, 100]


class CustomOrder(TimeStampedModel, SoftDeleteModel):
    """
    A bespoke clothing commission from a client to a specific vendor.

    The client can attach a product snapshot (product_snapshot_id) or
    an existing order snapshot (order_snapshot_id) as a style reference.
    
    Top-level bespoke commission contract.

    Client submits a design brief optionally referencing an existing product or
    order. Vendor reviews, sets an agreed price, and approves. The system then
    auto-seeds milestone payment tranches (30→50→70→100%).
    """

    # ── Reference ──────────────────────────────────────────────────
    reference = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        editable=False,
        help_text="Human-readable reference e.g. CO-20260526-0001",
    )


    # Parties
    client = models.ForeignKey(
        "authentication.UnifiedUser",
        on_delete=models.PROTECT,
        related_name="custom_orders_as_client",
        limit_choices_to={"role": "client"},
        help_text="The client who initiated the commission.",
        db_index=True,
    )
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        on_delete=models.PROTECT,
        related_name="custom_orders_as_vendor",
        limit_choices_to={"role": "vendor"},
        help_text="The vendor fulfilling the commission.",
        db_index=True,
    )

    # ── Content Design Brief ───────────────────────────────────────────────
    design_brief = models.TextField(
        help_text="Detailed description of the client's custom design requirements.",
    )    
    reference_images = models.JSONField(
        default=list,
        blank=True,
        help_text="List of uploaded image URLs for style reference.",
    )


    # ──  Optional Snapshot References (optional) ────────────────────────────
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


    # Financials ─────────────────────────────────────────────────
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
    currency = models.CharField(max_length=3, default="NGN")

    # Status machine
    status = models.CharField(
        max_length=20,
        choices=CustomOrderStatus.choices,
        default=CustomOrderStatus.DRAFT,
        db_index=True,
    )


    # ── Vendor Narration ──────────────────────────────────────────
    vendor_approval_note = models.TextField(
        blank=True,
        default="",
        help_text="Vendor's note when approving/declining the design brief.",
    )

    # Timestamps
    approved_at   = models.DateTimeField(null=True, blank=True)
    completed_at  = models.DateTimeField(null=True, blank=True)

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

    def save(self, *args, **kwargs) -> None:  # type: ignore[override]
        if not self.reference:
            self.reference = self._generate_reference()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference() -> str:
        import random
        import string
        from django.utils import timezone
        today = timezone.now().strftime("%Y%m%d")
        short = str(uuid.uuid4())[:6].upper()
        return f"CO-{today}-{short}"
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return f"CO-{suffix}"

    def __str__(self) -> str:
        return f"CustomOrder[{self.reference}] {self.status}"

    # ── Status machine helpers ────────────────────────────────────────────────

    def submit(self) -> None:
        """Client submits draft to vendor."""
        if self.status != CustomOrderStatus.DRAFT:
            raise ValueError(f"Cannot submit from status '{self.status}'")
        self.status = CustomOrderStatus.SUBMITTED
        self.save(update_fields=["status", "updated_at"])

    def approve(self, agreed_amount_ngn: Decimal, note: str = "") -> None:
        """Vendor approves and sets the agreed price."""
        if self.status != CustomOrderStatus.SUBMITTED:
            raise ValueError(f"Cannot approve from status '{self.status}'")
        self.status             = CustomOrderStatus.APPROVED
        self.agreed_amount_ngn  = agreed_amount_ngn
        self.vendor_approval_note = note
        self.approved_at        = timezone.now()
        self.save(update_fields=[
            "status", "agreed_amount_ngn", "vendor_approval_note", "approved_at", "updated_at"
        ])
        self.create_milestones()

    def start_production(self) -> None:
        """Marks order as in production (after first milestone paid)."""
        if self.status != CustomOrderStatus.APPROVED:
            raise ValueError(f"Cannot start production from status '{self.status}'")
        self.status = CustomOrderStatus.IN_PRODUCTION
        self.save(update_fields=["status", "updated_at"])

    def complete(self) -> None:
        """Vendor marks order complete after final payment."""
        if self.status != CustomOrderStatus.IN_PRODUCTION:
            raise ValueError(f"Cannot complete from status '{self.status}'")
        self.status       = CustomOrderStatus.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    def cancel(self) -> None:
        if self.status in (CustomOrderStatus.COMPLETED, CustomOrderStatus.CANCELLED):
            raise ValueError(f"Cannot cancel from status '{self.status}'")
        self.status = CustomOrderStatus.CANCELLED
        self.save(update_fields=["status", "updated_at"])

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


    # ── Business Logic Helpers For Milestone seeding ────────────────────────────────────────────────────

    def create_milestones(self) -> list["CustomOrderMilestone"]:
        """
        Create the 4 milestone payment tranches once vendor approves.
        Called by the approve service after setting agreed_amount_ngn.
        
        Auto-create the 4 milestone payment rows upon vendor approval.

        Uses the agreed_amount_ngn to compute each tranche's NGN value.
        Safe to call multiple times — skips if milestones already exist.
        """
        if self.milestones.exists():
            raise ValueError("agreed_amount_ngn must be set before creating milestones.")
        total = self.agreed_amount_ngn or self.budget_ngn
        milestones = []
        for pct in MILESTONE_PERCENTAGES:
            amount = (total * Decimal(pct) / Decimal(100)).quantize(Decimal("0.01"))
            milestones.append(
                CustomOrderMilestone(
                    custom_order=self,
                    milestone_pct=pct,
                    amount_ngn=amount,
                )
            )
        CustomOrderMilestone.objects.bulk_create(milestones)
        return milestones
        logger.info(
            "custom_order.models: seeded %d milestones for order %s",
            len(milestones), self.reference,
        )


class CustomOrderMilestone(TimeStampedModel, SoftDeleteModel):
    """
    Payment tranche for a bespoke custom order.

    4 rows per CustomOrder: 30%, 50%, 70%, 100%.    
    
    Each must be paid in sequence before the next is unlocked.
    Only one milestone is payable at a time (determined by service logic).
    """

    custom_order  = models.ForeignKey(
        CustomOrder,
        on_delete=models.CASCADE,
        related_name="milestones",
    )
    milestone_pct = models.PositiveSmallIntegerField(
        help_text="Percentage of total order this milestone covers: 30, 50, 70, or 100.",
    )
      # 30 | 50 | 70 | 100
    amount_ngn = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="NGN amount for this tranche.",
    )    
    
    payment_status = models.CharField(
        max_length=12,
        choices=MilestonePaymentStatus.choices,
        default=MilestonePaymentStatus.PENDING,
        db_index=True,
    )

    paid_at = models.DateTimeField(null=True, blank=True)
    transaction_ref = models.CharField(max_length=128, blank=True, default="")

    payment_reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="External payment provider reference.",
    )   


    class Meta:
        app_label  = "custom_order"
        verbose_name = "Custom Order Milestone"
        verbose_name_plural = "Custom Order Milestones"
        db_table = "custom_order_milestone"
        unique_together = [("custom_order", "milestone_pct")]
        ordering = ["milestone_pct"]


    def __str__(self) -> str:
        return (
            f"Milestone {self.milestone_pct}% "
            f"[{self.custom_order.reference}] — {self.payment_status}"
        )

    def mark_paid(self, transaction_ref: str = "") -> None:
        """Record milestone as paid."""
        self.payment_status = MilestonePaymentStatus.PAID
        self.paid_at        = timezone.now()
        self.transaction_ref = transaction_ref
        self.save(update_fields=["payment_status", "paid_at", "transaction_ref", "updated_at"])
