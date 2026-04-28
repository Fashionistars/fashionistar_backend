# apps/support/services/support_service.py
"""
Support Domain Service Layer — all mutations are atomic.

Rules:
  ─ ALL write operations use transaction.atomic().
  ─ Services delegate all reads to selectors (never query ORM in services).
  ─ Services NEVER use sync_to_async() — they are sync and called from
    async Ninja views via asyncio.get_event_loop().run_in_executor(None, ...).
  ─ Notification dispatch is fire-and-forget via Celery (never blocks caller).
  ─ Idempotency: creating a ticket for the same order_id returns existing ticket
    instead of creating a duplicate (prevents double-submission on mobile).
"""

import logging
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

User = get_user_model()
logger = logging.getLogger(__name__)


class SupportService:
    """
    Central service for support ticket mutations.

    All class methods are sync and wrapped in transaction.atomic().
    Call from async Ninja views via:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, functools.partial(SupportService.method, ...))
    """

    # ── Ticket Creation ───────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def create_ticket(user, data: dict) -> "SupportTicket":  # noqa: F821
        """
        Create a new support ticket for the given user.

        Idempotent per order_id: if a ticket with the same order_id already
        exists for this user and is not CLOSED, the existing ticket is returned.

        Args:
            user: The submitting UnifiedUser instance.
            data: Validated dict from SupportTicketWriteSerializer containing:
                  - title (str)
                  - description (str)
                  - category (str, TicketCategory value)
                  - priority (str, TicketPriority value, optional)
                  - order_id (UUID | None, optional)
                  - metadata (dict, optional)

        Returns:
            SupportTicket instance (new or existing).
        """
        from apps.support.models import SupportTicket, TicketStatus

        order_id = data.get("order_id")

        # Idempotency guard: one open ticket per order
        if order_id:
            existing = SupportTicket.objects.filter(
                submitter=user,
                order_id=order_id,
            ).exclude(status=TicketStatus.CLOSED).first()
            if existing:
                logger.info(
                    "SupportService.create_ticket: returning existing ticket=%s for order=%s",
                    existing.id,
                    order_id,
                )
                return existing

        ticket = SupportTicket.objects.create(
            submitter=user,
            title=data["title"],
            description=data["description"],
            category=data.get("category", "general"),
            priority=data.get("priority", "medium"),
            order_id=order_id,
            metadata=data.get("metadata", {}),
        )
        logger.info(
            "SupportService.create_ticket: created ticket=%s category=%s user=%s",
            ticket.id,
            ticket.category,
            user.id,
        )

        # Fire notification to submitter (async, non-blocking)
        SupportService._notify_ticket_created(ticket, user)

        return ticket

    # ── Thread Messages ───────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def add_message(
        author,
        ticket_id: UUID | str,
        body: str,
        *,
        is_staff: bool = False,
        attachments: list | None = None,
    ) -> "TicketMessage":  # noqa: F821
        """
        Append a reply to a ticket's message thread.

        Access rules (enforced here):
          - Non-staff users may only message their own tickets.
          - Staff may message any open ticket.
          - CLOSED tickets reject new messages.

        Args:
            author: The UnifiedUser adding the message.
            ticket_id: UUID of the SupportTicket.
            body: Message text.
            is_staff: True if the author is a staff member.
            attachments: List of Cloudinary public_ids (optional).

        Returns:
            TicketMessage instance.

        Raises:
            ValueError: If ticket not found, not owned, or closed.
        """
        from apps.support.models import SupportTicket, TicketMessage, TicketStatus

        try:
            if is_staff:
                ticket = SupportTicket.objects.select_for_update().get(id=ticket_id)
            else:
                ticket = SupportTicket.objects.select_for_update().get(
                    id=ticket_id,
                    submitter=author,
                )
        except SupportTicket.DoesNotExist:
            raise ValueError("Ticket not found or access denied.")

        if ticket.status == TicketStatus.CLOSED:
            raise ValueError("Cannot add messages to a closed ticket.")

        msg = TicketMessage.objects.create(
            ticket=ticket,
            author=author,
            body=body,
            is_staff_reply=is_staff,
            attachments=attachments or [],
        )

        # Auto-transition: non-staff reply moves ticket back to IN_REVIEW
        if not is_staff and ticket.status == TicketStatus.AWAITING_CLIENT:
            ticket.status = TicketStatus.IN_REVIEW
            ticket.save(update_fields=["status", "updated_at"])

        # Auto-transition: staff reply moves ticket to AWAITING_CLIENT
        if is_staff and ticket.status in (TicketStatus.OPEN, TicketStatus.IN_REVIEW):
            ticket.status = TicketStatus.AWAITING_CLIENT
            ticket.save(update_fields=["status", "updated_at"])

        logger.info(
            "SupportService.add_message: msg=%s on ticket=%s is_staff=%s",
            msg.id,
            ticket_id,
            is_staff,
        )
        return msg

    # ── Status Transitions ────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def update_status(
        staff_user,
        ticket_id: UUID | str,
        new_status: str,
        notes: str = "",
    ) -> "SupportTicket":  # noqa: F821
        """
        Staff-only status transition with optional resolution notes.

        Args:
            staff_user: UnifiedUser with is_staff=True.
            ticket_id: UUID of the SupportTicket.
            new_status: Target TicketStatus value.
            notes: Optional resolution/closure notes.

        Returns:
            Updated SupportTicket.

        Raises:
            PermissionError: If staff_user is not staff.
            ValueError: Forwarded from ticket.transition().
        """
        if not getattr(staff_user, "is_staff", False):
            raise PermissionError("Only staff members can update ticket status.")

        from apps.support.models import SupportTicket

        ticket = SupportTicket.objects.select_for_update().get(id=ticket_id)
        ticket.transition(new_status=new_status, notes=notes)

        logger.info(
            "SupportService.update_status: ticket=%s → %s by staff=%s",
            ticket_id,
            new_status,
            staff_user.id,
        )
        return ticket

    # ── Escalation ────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def escalate(
        staff_user,
        ticket_id: UUID | str,
        reason: str,
    ) -> "TicketEscalation":  # noqa: F821
        """
        Create or return a TicketEscalation for the given ticket.
        Idempotent — returns the existing escalation if one already exists.

        Also transitions the ticket to IN_REVIEW and assigns the escalating
        staff member.

        Args:
            staff_user: UnifiedUser with is_staff=True.
            ticket_id: UUID of the SupportTicket.
            reason: Text description of why escalation is needed.

        Returns:
            TicketEscalation instance.

        Raises:
            PermissionError: If caller is not staff.
            ValueError: If ticket is CLOSED.
        """
        if not getattr(staff_user, "is_staff", False):
            raise PermissionError("Only staff members can escalate tickets.")

        from apps.support.models import SupportTicket, TicketStatus, TicketEscalation, EscalationStatus

        ticket = SupportTicket.objects.select_for_update().get(id=ticket_id)

        if ticket.status == TicketStatus.CLOSED:
            raise ValueError("Cannot escalate a closed ticket.")

        escalation, created = TicketEscalation.objects.get_or_create(
            ticket=ticket,
            defaults={
                "escalated_by": staff_user,
                "reason": reason,
                "status": EscalationStatus.OPEN,
            },
        )

        if created:
            # Assign the escalating staff and move ticket to IN_REVIEW
            ticket.assigned_to = staff_user
            if ticket.status != TicketStatus.IN_REVIEW:
                ticket.status = TicketStatus.IN_REVIEW
            ticket.save(update_fields=["assigned_to", "status", "updated_at"])

            logger.info(
                "SupportService.escalate: created escalation=%s on ticket=%s",
                escalation.id,
                ticket_id,
            )

        return escalation

    # ── Resolution ────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def resolve(
        staff_user,
        ticket_id: UUID | str,
        resolution_notes: str,
    ) -> "SupportTicket":  # noqa: F821
        """
        Mark a ticket as RESOLVED and dispatch a resolution notification.

        Args:
            staff_user: UnifiedUser with is_staff=True.
            ticket_id: UUID of the SupportTicket.
            resolution_notes: Staff notes on how the ticket was resolved.

        Returns:
            Resolved SupportTicket.

        Raises:
            PermissionError: If caller is not staff.
        """
        from apps.support.models import TicketStatus

        ticket = SupportService.update_status(
            staff_user=staff_user,
            ticket_id=ticket_id,
            new_status=TicketStatus.RESOLVED,
            notes=resolution_notes,
        )

        # Notify the submitter of resolution
        SupportService._notify_ticket_resolved(ticket)

        return ticket

    # ── Internal Notification Helpers ─────────────────────────────────────────

    @staticmethod
    def _notify_ticket_created(ticket, user) -> None:
        """Fire-and-forget Celery notification: ticket created."""
        try:
            from apps.notification.services import send_notification
            send_notification(
                user=user,
                notification_type="system_alert",
                title="Support ticket opened",
                body=(
                    f"Your support ticket #{str(ticket.id)[:8].upper()} "
                    f"has been received. We'll respond within 24 hours."
                ),
                metadata={"ticket_id": str(ticket.id), "category": ticket.category},
            )
        except Exception:
            logger.warning(
                "SupportService._notify_ticket_created: notification failed for ticket=%s",
                ticket.id,
            )

    @staticmethod
    def _notify_ticket_resolved(ticket) -> None:
        """Fire-and-forget Celery notification: ticket resolved."""
        if not ticket.submitter:
            return
        try:
            from apps.notification.services import send_notification
            send_notification(
                user=ticket.submitter,
                notification_type="system_alert",
                title="Support ticket resolved",
                body=(
                    f"Your ticket #{str(ticket.id)[:8].upper()} has been resolved. "
                    f"Resolution: {ticket.resolution_notes[:120]}"
                ),
                metadata={"ticket_id": str(ticket.id)},
            )
        except Exception:
            logger.warning(
                "SupportService._notify_ticket_resolved: notification failed for ticket=%s",
                ticket.id,
            )
