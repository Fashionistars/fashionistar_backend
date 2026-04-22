# apps/client/urls.py
"""
Client Domain — DRF URL Patterns.

Mounted at: /api/v1/client/  (via backend/urls.py include)

Async Ninja endpoints are registered separately in:
  backend/urls.py → ninja_api.add_router("/client/", client_router)
"""
from django.urls import path

from apps.client.apis.sync.profile_views import (
    ClientAddressDetailView,
    ClientAddressListCreateView,
    ClientAddressSetDefaultView,
    ClientProfileView,
)

app_name = "client"

urlpatterns = [
    # ── Profile ────────────────────────────────────────────────────
    path("profile/", ClientProfileView.as_view(), name="profile"),

    # ── Addresses ──────────────────────────────────────────────────
    path("addresses/", ClientAddressListCreateView.as_view(), name="address-list"),
    path("addresses/<uuid:address_id>/", ClientAddressDetailView.as_view(), name="address-detail"),
    path(
        "addresses/<uuid:address_id>/set-default/",
        ClientAddressSetDefaultView.as_view(),
        name="address-set-default",
    ),
]
