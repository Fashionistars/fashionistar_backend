# apps/support/urls.py
"""
URL configuration for the Support domain.

DRF (sync) routes mounted at /api/v1/support/ via backend/urls.py.
Async Ninja routes are registered in backend/ninja_api.py.
"""

from django.urls import path

from apps.support.apis.sync import (
    SupportTicketListCreateView,
    SupportTicketDetailView,
    TicketMessageView,
    TicketStatusUpdateView,
    TicketEscalateView,
)
from apps.support.apis.sync.support_views import AdminTicketQueueView

app_name = "support"

urlpatterns = [
    # ── Client Ticket Endpoints ───────────────────────────────────────────────
    # GET  /api/v1/support/tickets/   — list user tickets
    # POST /api/v1/support/tickets/   — open new ticket
    path("tickets/", SupportTicketListCreateView.as_view(), name="ticket-list-create"),

    # GET  /api/v1/support/tickets/<ticket_id>/   — ticket detail + thread
    path("tickets/<uuid:ticket_id>/", SupportTicketDetailView.as_view(), name="ticket-detail"),

    # POST /api/v1/support/tickets/<ticket_id>/messages/  — add thread reply
    path("tickets/<uuid:ticket_id>/messages/", TicketMessageView.as_view(), name="ticket-messages"),

    # ── Staff Endpoints (IsAdminUser guard) ───────────────────────────────────
    # PATCH /api/v1/support/tickets/<ticket_id>/status/  — update status
    path("tickets/<uuid:ticket_id>/status/", TicketStatusUpdateView.as_view(), name="ticket-status"),

    # POST /api/v1/support/tickets/<ticket_id>/escalate/ — escalate ticket
    path("tickets/<uuid:ticket_id>/escalate/", TicketEscalateView.as_view(), name="ticket-escalate"),

    # GET /api/v1/support/admin/queue/  — staff ticket queue (all users)
    path("admin/queue/", AdminTicketQueueView.as_view(), name="admin-queue"),
]
