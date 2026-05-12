# apps/support/tests/test_support_api.py
"""
Support Domain — pytest test suite.

Coverage:
  - Ticket creation (happy path + idempotency guard)
  - Ticket list scoping (client sees only own tickets)
  - Thread message posting (client + staff roles)
  - Auto status transitions on message posting
  - Staff-only status update endpoint
  - Escalation idempotency
  - Permission matrix (unauthenticated, client, staff)
  - CLOSED ticket guard (no new messages)

Test pattern mirrors apps/chat/tests — uses pytest-django factory helpers,
no external dependencies, pure DB testing with @pytest.mark.django_db.
"""

import uuid
import pytest
from django.urls import reverse

from apps.authentication.models import UnifiedUser
from apps.support.models import (
    SupportTicket,
    TicketMessage,
    TicketEscalation,
    TicketStatus,
    TicketPriority,
    TicketCategory,
    EscalationStatus,
)
from apps.support.services import SupportService


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client_user(db):
    return UnifiedUser.objects.create_user(
        email="client@test.com",
        password="testpass123",
        is_active=True,
    )


@pytest.fixture
def staff_user(db):
    return UnifiedUser.objects.create_user(
        email="staff@test.com",
        password="testpass123",
        is_active=True,
        is_staff=True,
    )


@pytest.fixture
def other_user(db):
    return UnifiedUser.objects.create_user(
        email="other@test.com",
        password="testpass123",
        is_active=True,
    )


@pytest.fixture
def open_ticket(db, client_user):
    """A fresh OPEN ticket owned by client_user."""
    return SupportService.create_ticket(
        user=client_user,
        data={
            "title": "My order was not delivered",
            "description": "I placed order FSN-ORD-001 but it has not arrived.",
            "category": TicketCategory.ORDER_DISPUTE,
            "priority": TicketPriority.HIGH,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. TICKET CREATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTicketCreation:

    def test_create_ticket_success(self, client_user):
        ticket = SupportService.create_ticket(
            user=client_user,
            data={
                "title": "Product quality issue",
                "description": "The dress I received was not as described.",
                "category": TicketCategory.PRODUCT_COMPLAINT,
            },
        )
        assert ticket.pk is not None
        assert ticket.status == TicketStatus.OPEN
        assert ticket.submitter == client_user
        assert ticket.category == TicketCategory.PRODUCT_COMPLAINT
        assert ticket.priority == TicketPriority.MEDIUM  # default

    def test_create_ticket_idempotent_same_order(self, client_user):
        """Same order_id → returns existing ticket, no duplicate."""
        order_id = uuid.uuid4()
        data = {
            "title": "Dispute #1",
            "description": "Payment was deducted but order not placed.",
            "category": TicketCategory.PAYMENT_ISSUE,
            "order_id": order_id,
        }
        ticket1 = SupportService.create_ticket(user=client_user, data=data)
        ticket2 = SupportService.create_ticket(user=client_user, data=data)

        assert ticket1.id == ticket2.id
        assert SupportTicket.objects.filter(order_id=order_id).count() == 1

    def test_create_ticket_different_order_creates_new(self, client_user):
        """Different order_id → creates separate tickets."""
        t1 = SupportService.create_ticket(
            user=client_user,
            data={
                "title": "Issue A",
                "description": "Desc A",
                "order_id": uuid.uuid4(),
            },
        )
        t2 = SupportService.create_ticket(
            user=client_user,
            data={
                "title": "Issue B",
                "description": "Desc B",
                "order_id": uuid.uuid4(),
            },
        )
        assert t1.id != t2.id

    def test_create_ticket_no_order_always_new(self, client_user):
        """No order_id → no idempotency, always creates new."""
        t1 = SupportService.create_ticket(
            user=client_user,
            data={"title": "General question A", "description": "..."},
        )
        t2 = SupportService.create_ticket(
            user=client_user,
            data={"title": "General question B", "description": "..."},
        )
        assert t1.id != t2.id


# ─────────────────────────────────────────────────────────────────────────────
# 2. THREAD MESSAGES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTicketMessages:

    def test_client_can_message_own_ticket(self, client_user, open_ticket):
        msg = SupportService.add_message(
            author=client_user,
            ticket_id=open_ticket.id,
            body="Here is more info about the issue.",
            is_staff=False,
        )
        assert msg.body == "Here is more info about the issue."
        assert msg.is_staff_reply is False
        assert TicketMessage.objects.filter(ticket=open_ticket).count() == 1

    def test_staff_can_message_any_ticket(self, staff_user, open_ticket):
        msg = SupportService.add_message(
            author=staff_user,
            ticket_id=open_ticket.id,
            body="We are looking into this for you.",
            is_staff=True,
        )
        assert msg.is_staff_reply is True

    def test_client_cannot_message_other_user_ticket(self, other_user, open_ticket):
        with pytest.raises(ValueError, match="access denied"):
            SupportService.add_message(
                author=other_user,
                ticket_id=open_ticket.id,
                body="Trying to access someone else's ticket.",
                is_staff=False,
            )

    def test_cannot_message_closed_ticket(self, client_user, staff_user, open_ticket):
        # Close the ticket first
        SupportService.update_status(
            staff_user=staff_user,
            ticket_id=open_ticket.id,
            new_status=TicketStatus.CLOSED,
            notes="Issue resolved.",
        )
        with pytest.raises(ValueError, match="closed"):
            SupportService.add_message(
                author=client_user,
                ticket_id=open_ticket.id,
                body="Following up.",
                is_staff=False,
            )

    def test_staff_reply_auto_transitions_to_awaiting_client(self, staff_user, open_ticket):
        """Staff reply on OPEN ticket → status moves to AWAITING_CLIENT."""
        SupportService.add_message(
            author=staff_user,
            ticket_id=open_ticket.id,
            body="Please provide your order number.",
            is_staff=True,
        )
        open_ticket.refresh_from_db()
        assert open_ticket.status == TicketStatus.AWAITING_CLIENT

    def test_client_reply_auto_transitions_back_to_in_review(self, client_user, staff_user, open_ticket):
        """Client reply on AWAITING_CLIENT ticket → status moves back to IN_REVIEW."""
        # Move to AWAITING_CLIENT
        SupportService.add_message(
            author=staff_user,
            ticket_id=open_ticket.id,
            body="Please reply with your order number.",
            is_staff=True,
        )
        open_ticket.refresh_from_db()
        assert open_ticket.status == TicketStatus.AWAITING_CLIENT

        # Client replies
        SupportService.add_message(
            author=client_user,
            ticket_id=open_ticket.id,
            body="My order number is FSN-ORD-001.",
            is_staff=False,
        )
        open_ticket.refresh_from_db()
        assert open_ticket.status == TicketStatus.IN_REVIEW


# ─────────────────────────────────────────────────────────────────────────────
# 3. STATUS TRANSITIONS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStatusTransitions:

    def test_staff_can_update_status(self, staff_user, open_ticket):
        ticket = SupportService.update_status(
            staff_user=staff_user,
            ticket_id=open_ticket.id,
            new_status=TicketStatus.IN_REVIEW,
        )
        assert ticket.status == TicketStatus.IN_REVIEW

    def test_non_staff_cannot_update_status(self, client_user, open_ticket):
        with pytest.raises(PermissionError):
            SupportService.update_status(
                staff_user=client_user,  # not staff
                ticket_id=open_ticket.id,
                new_status=TicketStatus.IN_REVIEW,
            )

    def test_resolve_sets_resolved_at(self, staff_user, open_ticket):
        ticket = SupportService.resolve(
            staff_user=staff_user,
            ticket_id=open_ticket.id,
            resolution_notes="Refund issued successfully.",
        )
        assert ticket.status == TicketStatus.RESOLVED
        assert ticket.resolved_at is not None
        assert ticket.resolution_notes == "Refund issued successfully."

    def test_cannot_transition_from_closed(self, staff_user, open_ticket):
        # Close the ticket
        SupportService.update_status(
            staff_user=staff_user,
            ticket_id=open_ticket.id,
            new_status=TicketStatus.CLOSED,
        )
        with pytest.raises(ValueError, match="Cannot transition a CLOSED ticket"):
            SupportService.update_status(
                staff_user=staff_user,
                ticket_id=open_ticket.id,
                new_status=TicketStatus.OPEN,
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. ESCALATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestEscalation:

    def test_staff_can_escalate(self, staff_user, open_ticket):
        escalation = SupportService.escalate(
            staff_user=staff_user,
            ticket_id=open_ticket.id,
            reason="Large financial dispute — vendor refusing refund.",
        )
        assert escalation.pk is not None
        assert escalation.status == EscalationStatus.OPEN
        assert escalation.ticket == open_ticket

    def test_escalation_is_idempotent(self, staff_user, open_ticket):
        e1 = SupportService.escalate(
            staff_user=staff_user,
            ticket_id=open_ticket.id,
            reason="Duplicate escalation test.",
        )
        e2 = SupportService.escalate(
            staff_user=staff_user,
            ticket_id=open_ticket.id,
            reason="Second call — should return existing.",
        )
        assert e1.id == e2.id
        assert TicketEscalation.objects.filter(ticket=open_ticket).count() == 1

    def test_non_staff_cannot_escalate(self, client_user, open_ticket):
        with pytest.raises(PermissionError):
            SupportService.escalate(
                staff_user=client_user,
                ticket_id=open_ticket.id,
                reason="Client trying to escalate.",
            )

    def test_cannot_escalate_closed_ticket(self, staff_user, open_ticket):
        SupportService.update_status(
            staff_user=staff_user,
            ticket_id=open_ticket.id,
            new_status=TicketStatus.CLOSED,
        )
        with pytest.raises(ValueError, match="closed"):
            SupportService.escalate(
                staff_user=staff_user,
                ticket_id=open_ticket.id,
                reason="Too late.",
            )


# ─────────────────────────────────────────────────────────────────────────────
# 5. API PERMISSION MATRIX (DRF endpoints)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAPIPermissions:

    def test_unauthenticated_cannot_list_tickets(self, client):
        url = reverse("support:ticket-list-create")
        res = client.get(url)
        assert res.status_code == 401

    def test_client_can_list_own_tickets(self, client, client_user):
        client.force_login(client_user)
        url = reverse("support:ticket-list-create")
        res = client.get(url)
        assert res.status_code == 200

    def test_client_cannot_access_admin_queue(self, client, client_user):
        client.force_login(client_user)
        url = reverse("support:admin-queue")
        res = client.get(url)
        assert res.status_code == 403

    def test_staff_can_access_admin_queue(self, client, staff_user):
        client.force_login(staff_user)
        url = reverse("support:admin-queue")
        res = client.get(url)
        assert res.status_code == 200

    def test_client_cannot_update_status(self, client, client_user, open_ticket):
        client.force_login(client_user)
        url = reverse("support:ticket-status", kwargs={"ticket_id": open_ticket.id})
        res = client.patch(
            url,
            data={"status": "resolved"},
            content_type="application/json",
        )
        assert res.status_code == 403

    def test_client_cannot_access_other_ticket_detail(self, client, other_user, open_ticket):
        client.force_login(other_user)
        url = reverse("support:ticket-detail", kwargs={"ticket_id": open_ticket.id})
        res = client.get(url)
        # Returns 404 (not found in scope) rather than 403
        assert res.status_code == 404
