# apps/chat/admin_backend/urls.py
from django.urls import path
from .views import AdminResolveEscalationView

urlpatterns = [
    path("escalations/<str:escalation_id>/resolve/", AdminResolveEscalationView.as_view(), name="admin-chat-escalation-resolve"),
]
