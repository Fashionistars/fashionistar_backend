# apps/client/admin_backend/urls.py
"""
DRF URL patterns for the client admin domain.
Mounted under /api/admin/client/ by apps/admin_backend/urls.py.
"""

from django.urls import path
from .views import AdminClientProfileUpdateView

urlpatterns = [
    path("profiles/<str:profile_id>/", AdminClientProfileUpdateView.as_view(), name="admin-client-profile-update"),
]
