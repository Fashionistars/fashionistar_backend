# apps/support/models/support_ticket.py
"""
Support domain models for Fashionistar.

Architecture:
  - SupportTicket: one ticket per issue, scoped to the submitting user.
  - TicketMessage: threaded replies within a ticket (client + staff).
  - TicketEscalation: admin takeover record, one per ticket.

Design decisions:
  - UUID PKs for all models (consistent with chat, order domains).
  - SET_NULL on user FK: ticket history preserved after account deletion
    (regulatory / audit trail requirement).
  - order_id stored as UUIDField (not FK) to decouple support from order
    domain migrations — cross-domain reference via metadata, not FK.
  - metadata JSONField carries arbitrary context (order_number, product_slug,
    payment_reference, etc.) without FK coupling.
  - Financial/compliance tickets must be retained 7 years.
    Use soft-closure (status=CLOSED) — never hard-delete.
  - TicketMessage.is_staff_reply controls UI rendering and access control.
"""

import logging
import uuid

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel

User = get_user_model()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class TicketStatus(models.TextChoices):
    OPEN              = "open",              _("Open")
    AWAITING_CLIENT   = "awaiting_client",   _("Awaiting Client Response")
    AWAITING_VENDOR   = "awaiting_vendor",   _("Awaiting Vendor Response")
    IN_REVIEW         = "in_review",         _("Under Staff Review")
    RESOLVED          = "resolved",          _("Resolved")
    CLOSED            = "closed",            _("Closed")


class TicketPriority(models.TextChoices):
    LOW    = "low",    _("Low")
    MEDIUM = "medium", _("Medium")
    HIGH   = "high",   _("High")
    URGENT = "urgent", _("Urgent")


class TicketCategory(models.TextChoices):
    ORDER_DISPUTE      = "order_dispute",      _("Order Dispute")
    PAYMENT_ISSUE      = "payment_issue",      _("Payment Issue")
    PRODUCT_COMPLAINT  = "product_complaint",  _("Product Complaint")
    VENDOR_CONDUCT     = "vendor_conduct",     _("Vendor Conduct")
    DELIVERY_PROBLEM   = "delivery_problem",   _("Delivery Problem")
    REFUND_REQUEST     = "refund_request",     _("Refund Request")
    GENERAL            = "general",            _("General Inquiry")


# ─────────────────────────────────────────────────────────────────────────────
# 1. SUPPORT TICKET
# ─────────────────────────────────────────────────────────────────────────────

class SupportTicket(TimeStampedModel):
    """
    A customer support ticket.

    Lifecycle:
      OPEN → (staff picks up) → IN_REVIEW
           → (staff replies) → AWAITING_CLIENT | AWAITING_VENDOR
           → (client/vendor replies) → IN_REVIEW
           → (issue resolved) → RESOLVED → CLOSED

    Financial dispute tickets MUST be retained for 7 years.
    Status CLOSED is the only terminal state — never hard-delete.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Submitter — SET_NULL preserves ticket for audit trail after account deletion
    submitter = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submitted_tickets",
        help_text="SET_NULL: ticket retained for audit after account deletion.",
    )

    # Cross-domain reference (no FK coupling to order domain)
    order_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Reference to order.Order.id — stored as UUID, not FK.",
    )

    # Classification
    category = models.CharField(
        max_length=30,
        choices=TicketCategory.choices,
        default=TicketCategory.GENERAL,
        db_index=True,
    )
    priority = models.CharField(
        max_length=10,
        choices=TicketPriority.choices,
        default=TicketPriority.MEDIUM,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.OPEN,
        db_index=True,
    )

    # Content
    title       = models.CharField(max_length=300)
    description = models.TextField()

    # Cross-domain context (order_number, product_slug, payment_ref, etc.)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Arbitrary context for this ticket. "
            "E.g. {'order_number': 'FSN-ORD-ABC', 'product_slug': 'silk-gown'}."
        ),
    )

    # Staff assignment
    assigned_to = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tickets",
        help_text="Staff member handling this ticket.",
    )

    # Resolution
    resolution_notes = models.TextField(blank=True)
    resolved_at      = models.DateTimeField(null=True, blank=True)
    closed_at        = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = _("Support Ticket")
        verbose_name_plural = _("Support Tickets")
        ordering            = ["-created_at"]
        indexes             = [
            models.Index(
                fields=["submitter", "status"],
                name="idx_ticket_submitter_status",
            ),
            models.Index(
                fields=["status", "priority"],
                name="idx_ticket_status_priority",
            ),
            models.Index(
                fields=["category", "created_at"],
                name="idx_ticket_category_created",
            ),
            models.Index(
                fields=["order_id"],
                name="idx_ticket_order_id",
            ),
        ]

    def __str__(self) -> str:
        return f"Ticket {self.id!s:.8} [{self.status}] — {self.title[:60]}"

    @property
    def is_open(self) -> bool:
        return self.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED)

    @property
    def is_resolved(self) -> bool:
        return self.status == TicketStatus.RESOLVED

    @transaction.atomic
    def transition(self, new_status: str, notes: str = "") -> None:
        """
        Atomic status machine transition.
        Enforces CLOSED as terminal — no transitions out of CLOSED.

        Args:
            new_status: Target TicketStatus value.
            notes: Optional resolution notes (written to resolution_notes on RESOLVED).
        """
        if self.status == TicketStatus.CLOSED:
            raise ValueError("Cannot transition a CLOSED ticket.")

        now = timezone.now()
        self.status = new_status

        if new_status == TicketStatus.RESOLVED:
            if notes:
                self.resolution_notes = notes
            self.resolved_at = now

        if new_status == TicketStatus.CLOSED:
            self.closed_at = now

        self.save(update_fields=["status", "resolution_notes", "resolved_at", "closed_at", "updated_at"])
        logger.info(
            "SupportTicket transition: id=%s → status=%s",
            self.id,
            new_status,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. TICKET MESSAGE (Threaded Reply)
# ─────────────────────────────────────────────────────────────────────────────

class TicketMessage(TimeStampedModel):
    """
    A single reply in the threaded support conversation for a ticket.

    Access rules (enforced at service layer):
      - Client submitters can only add messages to their own open tickets.
      - Staff with is_staff=True can add messages to any ticket.
      - is_staff_reply controls UI differentiation (staff badge, green bubble).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_messages",
        help_text="SET_NULL: message retained for audit after account deletion.",
    )

    body          = models.TextField()
    is_staff_reply = models.BooleanField(
        default=False,
        help_text="True if sent by a staff/admin user.",
    )

    # Optional attachments (list of Cloudinary public_ids / URLs)
    attachments = models.JSONField(
        default=list,
        blank=True,
        help_text="List of Cloudinary attachment public_ids.",
    )

    class Meta:
        verbose_name        = _("Ticket Message")
        verbose_name_plural = _("Ticket Messages")
        ordering            = ["created_at"]
        indexes             = [
            models.Index(
                fields=["ticket", "created_at"],
                name="idx_ticketmsg_ticket_created",
            ),
        ]

    def __str__(self) -> str:
        role = "Staff" if self.is_staff_reply else "Client"
        return f"[{role}] Msg on Ticket {self.ticket_id!s:.8}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. TICKET ESCALATION
# ─────────────────────────────────────────────────────────────────────────────

class EscalationStatus(models.TextChoices):
    OPEN         = "open",         _("Open")
    UNDER_REVIEW = "under_review", _("Under Review")
    RESOLVED     = "resolved",     _("Resolved")
    DISMISSED    = "dismissed",    _("Dismissed")


class TicketEscalation(TimeStampedModel):
    """
    An admin escalation record for a SupportTicket.
    One-to-one per ticket — only one active escalation allowed.

    Created by staff when a ticket requires senior admin oversight
    (e.g., large financial dispute, vendor misconduct, legal risk).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ticket = models.OneToOneField(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="escalation",
    )
    escalated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="initiated_escalations",
    )
    assigned_admin = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_escalations",
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=EscalationStatus.choices,
        default=EscalationStatus.OPEN,
        db_index=True,
    )
    resolution_notes = models.TextField(blank=True)
    resolved_at      = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = _("Ticket Escalation")
        verbose_name_plural = _("Ticket Escalations")
        ordering            = ["-created_at"]

    def __str__(self) -> str:
        return f"Escalation [{self.status}] on Ticket {self.ticket_id!s:.8}"
