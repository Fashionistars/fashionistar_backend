# apps/support/admin_backend/urls.py
from django.urls import path
from .views import AdminAssignTicketView, AdminResolveTicketView

urlpatterns = [
    path("<str:ticket_id>/assign/", AdminAssignTicketView.as_view(), name="admin-ticket-assign"),
    path("<str:ticket_id>/resolve/", AdminResolveTicketView.as_view(), name="admin-ticket-resolve"),
]
