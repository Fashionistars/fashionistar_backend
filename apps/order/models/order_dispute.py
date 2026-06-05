# apps/order/models/order_dispute.py
"""
OrderDispute — escrow-hold trigger and dispute resolution workflow.

Architecture Rules:
  - SoftDeleteModel + TimeStampedModel (disputes can be archived, not hard-deleted).
  - Opening a dispute MUST trigger escrow_hold via EscrowService (in OrderService).
  - Evidence files stored as Cloudinary public_ids in a JSONField (two-phase upload).
  - resolution_outcome is write-once — once set, the dispute is immutable.
  - Moderator assignment tracked explicitly for SLA accountability.
  - All mutations inside transaction.atomic() + select_for_update() on parent Order.

Dispute lifecycle:
  1. CLIENT opens (status=OPEN, escrow_held=True set by service layer)
  2. VENDOR responds (status=VENDOR_RESPONDED, evidence added)
  3. MODERATOR reviews (status=UNDER_REVIEW, assigned_moderator set)
  4. Resolution: RESOLVED_BUYER / RESOLVED_VENDOR / ESCALATED / CLOSED
"""

from __future__ import annotations

from cloudinary.models import CloudinaryField
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteModel, TimeStampedModel


class OrderDispute(TimeStampedModel, SoftDeleteModel):
    """
    Customer or vendor dispute on a specific order.

    Opening a dispute triggers an escrow hold — funds are locked
    until the dispute is resolved or escalated to platform moderators.

    Attributes:
        order: The disputed Order.
        opened_by: User who filed the dispute (CLIENT or VENDOR).
        reason: Categorical reason code.
        description: Detailed description of the issue.
        client_evidence: Cloudinary public_ids of client-uploaded evidence.
        vendor_evidence: Cloudinary public_ids of vendor-uploaded evidence.
        status: Current dispute workflow stage.
        resolution_outcome: Final resolution decision (write-once).
        resolution_note: Moderator's reasoning for the decision.
        assigned_moderator: Staff user managing the dispute.
        escrow_held: True if funds are currently locked in escrow.
        refund_amount: Amount to refund to client on resolution (if any).
        resolved_at: Timestamp of final resolution.
        sla_deadline: When the dispute must be resolved by (SLA enforcement).
    """

    class Reason(models.TextChoices):
        NOT_RECEIVED = "not_received", _("Item Not Received")
        NOT_AS_DESCRIBED = "not_as_described", _("Item Not as Described")
        QUALITY_ISSUE = "quality_issue", _("Quality Issue")
        WRONG_ITEM = "wrong_item", _("Wrong Item Sent")
        MEASUREMENT_MISMATCH = "measurement_mismatch", _("Measurement Mismatch")
        LATE_DELIVERY = "late_delivery", _("Late Delivery")
        VENDOR_UNRESPONSIVE = "vendor_unresponsive", _("Vendor Unresponsive")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        VENDOR_RESPONDED = "vendor_responded", _("Vendor Responded")
        UNDER_REVIEW = "under_review", _("Under Moderator Review")
        RESOLVED_BUYER = "resolved_buyer", _("Resolved — Buyer Wins")
        RESOLVED_VENDOR = "resolved_vendor", _("Resolved — Vendor Wins")
        ESCALATED = "escalated", _("Escalated to Senior Moderator")
        CLOSED = "closed", _("Closed Without Resolution")

    order = models.OneToOneField(
        "order.Order",
        on_delete=models.CASCADE,
        related_name="dispute",
        verbose_name=_("Order"),
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="opened_disputes",
        verbose_name=_("Opened By"),
    )
    reason = models.CharField(
        max_length=25,
        choices=Reason.choices,
        db_index=True,
        verbose_name=_("Reason"),
    )
    description = models.TextField(verbose_name=_("Description"))

    # Evidence: ordered lists of Cloudinary public_ids
    client_evidence = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Client Evidence"),
        help_text=_("List of Cloudinary public_ids uploaded by the client."),
    )
    vendor_evidence = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Vendor Evidence"),
        help_text=_("List of Cloudinary public_ids uploaded by the vendor."),
    )

    # Status + resolution
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
        verbose_name=_("Status"),
    )
    resolution_outcome = models.CharField(
        max_length=20,
        choices=Status.choices,
        blank=True,
        verbose_name=_("Resolution Outcome"),
        help_text=_("Write-once — set only on final resolution."),
    )
    resolution_note = models.TextField(
        blank=True,
        verbose_name=_("Resolution Note"),
        help_text=_("Moderator's reasoning for the resolution decision."),
    )
    assigned_moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_disputes",
        verbose_name=_("Assigned Moderator"),
    )

    # Escrow + financials
    escrow_held = models.BooleanField(
        default=True,
        verbose_name=_("Escrow Held"),
        help_text=_("True = funds locked in escrow during dispute."),
    )
    refund_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Refund Amount"),
        help_text=_("Amount to refund to client if resolved in their favour."),
    )

    # SLA enforcement
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Resolved At"),
    )
    sla_deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("SLA Deadline"),
        help_text=_("Platform-enforced resolution deadline (typically 7 days)."),
    )

    class Meta:
        verbose_name = _("Order Dispute")
        verbose_name_plural = _("Order Disputes")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="od_status_created_idx"),
            models.Index(fields=["assigned_moderator", "status"], name="od_mod_status_idx"),
            models.Index(fields=["sla_deadline", "status"], name="od_sla_idx"),
        ]

    def __str__(self) -> str:
        return f"Dispute[{self.status}] — Order#{self.order_id}"
