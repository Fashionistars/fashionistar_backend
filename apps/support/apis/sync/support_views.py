# apps/support/apis/sync/support_views.py
"""
DRF synchronous views for the Support domain.

Endpoints:
  GET    /api/v1/support/tickets/                     — List user's tickets
  POST   /api/v1/support/tickets/                     — Open a new ticket
  GET    /api/v1/support/tickets/<id>/                — Ticket detail + thread
  POST   /api/v1/support/tickets/<id>/messages/       — Add thread message
  PATCH  /api/v1/support/tickets/<id>/status/         — Staff status update
  POST   /api/v1/support/tickets/<id>/escalate/       — Staff escalation

Security:
  - All views require IsAuthenticated + IsAuthenticatedAndActive.
  - Staff-only endpoints additionally guard with IsAdminUser.
  - Client endpoints are scoped to request.user — no cross-user access.
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.views import APIView

from apps.common.renderers import CustomJSONRenderer, success_response, error_response
from apps.common.permissions import IsAuthenticatedAndActive
from apps.support.selectors import (
    get_ticket_or_none,
    get_user_tickets,
    get_admin_open_tickets,
)
from apps.support.serializers import (
    SupportTicketSerializer,
    SupportTicketListSerializer,
    SupportTicketWriteSerializer,
    TicketMessageSerializer,
    TicketMessageWriteSerializer,
    TicketStatusUpdateSerializer,
    TicketEscalateSerializer,
    TicketEscalationSerializer,
)
from apps.support.services import SupportService

logger = logging.getLogger(__name__)

_RENDERERS = [CustomJSONRenderer, BrowsableAPIRenderer]
_AUTH      = [IsAuthenticated, IsAuthenticatedAndActive]
_STAFF     = [IsAuthenticated, IsAuthenticatedAndActive, IsAdminUser]


# ─────────────────────────────────────────────────────────────────────────────
# TICKET LIST + CREATE
# ─────────────────────────────────────────────────────────────────────────────

class SupportTicketListCreateView(APIView):
    """
    GET  /api/v1/support/tickets/   — Return authenticated user's ticket feed.
    POST /api/v1/support/tickets/   — Open a new ticket (idempotent per order_id).
    """
    renderer_classes  = _RENDERERS
    permission_classes = _AUTH

    def get(self, request):
        status_filter   = request.query_params.get("status")
        category_filter = request.query_params.get("category")

        qs = get_user_tickets(
            user_id=request.user.id,
            status=status_filter,
            category=category_filter,
            limit=50,
        )
        return success_response(data=SupportTicketListSerializer(qs, many=True).data)

    def post(self, request):
        serializer = SupportTicketWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        try:
            ticket = SupportService.create_ticket(
                user=request.user,
                data=serializer.validated_data,
            )
        except Exception as exc:
            logger.exception("SupportTicketListCreateView.post: error for user=%s", request.user.id)
            return error_response(
                message=f"Failed to open ticket: {exc}",
                status=status.HTTP_400_BAD_REQUEST,
            )
        return success_response(
            data=SupportTicketSerializer(ticket).data,
            message="Support ticket opened successfully.",
            status=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# TICKET DETAIL
# ─────────────────────────────────────────────────────────────────────────────

class SupportTicketDetailView(APIView):
    """
    GET /api/v1/support/tickets/<ticket_id>/
    Returns full ticket detail including message thread and escalation.
    Scoped to the authenticated user (staff sees all via admin queue).
    """
    renderer_classes  = _RENDERERS
    permission_classes = _AUTH

    def get(self, request, ticket_id):
        # Staff can see any ticket; clients only their own
        if request.user.is_staff:
            from apps.support.models import SupportTicket
            ticket = (
                SupportTicket.objects
                .select_related("submitter", "assigned_to")
                .prefetch_related("messages__author", "escalation")
                .filter(id=ticket_id)
                .first()
            )
        else:
            ticket = get_ticket_or_none(ticket_id=ticket_id, user_id=request.user.id)

        if not ticket:
            return error_response(
                message="Ticket not found.",
                status=status.HTTP_404_NOT_FOUND,
            )
        return success_response(data=SupportTicketSerializer(ticket).data)


# ─────────────────────────────────────────────────────────────────────────────
# TICKET MESSAGES
# ─────────────────────────────────────────────────────────────────────────────

class TicketMessageView(APIView):
    """
    POST /api/v1/support/tickets/<ticket_id>/messages/
    Add a threaded reply to a ticket.
    Staff replies are differentiated via is_staff_reply flag.
    """
    renderer_classes  = _RENDERERS
    permission_classes = _AUTH

    def post(self, request, ticket_id):
        serializer = TicketMessageWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        try:
            msg = SupportService.add_message(
                author=request.user,
                ticket_id=ticket_id,
                body=serializer.validated_data["body"],
                is_staff=request.user.is_staff,
                attachments=serializer.validated_data.get("attachments", []),
            )
        except ValueError as exc:
            return error_response(
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("TicketMessageView.post: error for ticket=%s", ticket_id)
            return error_response(
                message="Failed to add message.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=TicketMessageSerializer(msg).data,
            message="Message added.",
            status=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# STAFF: STATUS UPDATE
# ─────────────────────────────────────────────────────────────────────────────

class TicketStatusUpdateView(APIView):
    """
    PATCH /api/v1/support/tickets/<ticket_id>/status/
    Staff-only endpoint: transition ticket status with optional notes.
    """
    renderer_classes  = _RENDERERS
    permission_classes = _STAFF

    def patch(self, request, ticket_id):
        serializer = TicketStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        try:
            ticket = SupportService.update_status(
                staff_user=request.user,
                ticket_id=ticket_id,
                new_status=serializer.validated_data["status"],
                notes=serializer.validated_data.get("notes", ""),
            )
        except (ValueError, PermissionError) as exc:
            return error_response(
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("TicketStatusUpdateView.patch: error for ticket=%s", ticket_id)
            return error_response(
                message="Status update failed.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=SupportTicketSerializer(ticket).data,
            message=f"Ticket status updated to '{ticket.status}'.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# STAFF: ESCALATION
# ─────────────────────────────────────────────────────────────────────────────

class TicketEscalateView(APIView):
    """
    POST /api/v1/support/tickets/<ticket_id>/escalate/
    Staff-only endpoint: create or return a TicketEscalation.
    Idempotent — safe to call twice.
    """
    renderer_classes  = _RENDERERS
    permission_classes = _STAFF

    def post(self, request, ticket_id):
        serializer = TicketEscalateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        try:
            escalation = SupportService.escalate(
                staff_user=request.user,
                ticket_id=ticket_id,
                reason=serializer.validated_data["reason"],
            )
        except (ValueError, PermissionError) as exc:
            return error_response(
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("TicketEscalateView.post: error for ticket=%s", ticket_id)
            return error_response(
                message="Escalation failed.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=TicketEscalationSerializer(escalation).data,
            message="Ticket escalated for admin review.",
            status=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# STAFF: ADMIN QUEUE
# ─────────────────────────────────────────────────────────────────────────────

class AdminTicketQueueView(APIView):
    """
    GET /api/v1/support/admin/queue/
    Staff-only: full ticket queue (all open tickets, any user).
    Supports ?status=&priority= filters.
    """
    renderer_classes  = _RENDERERS
    permission_classes = _STAFF

    def get(self, request):
        status_filter   = request.query_params.get("status")
        priority_filter = request.query_params.get("priority")
        qs = get_admin_open_tickets(
            status=status_filter,
            priority=priority_filter,
            limit=100,
        )
        return success_response(data=SupportTicketListSerializer(qs, many=True).data)
