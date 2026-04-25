# apps/common/urls.py
"""
Common Utilities URL Configuration — v1

All endpoints follow the /api/v1/ convention, matching auth endpoints.

Endpoints:
  # GET  /api/v1/health/                        — Load-balancer health probe
  POST /api/v1/upload/presign/                — Cloudinary signed upload token (JWT required)
  POST /api/v1/upload/webhook/cloudinary/     — Cloudinary HMAC-signed event receiver
"""
from django.urls import path
from apps.common.views import CloudinaryPresignView, CloudinaryWebhookView
from apps.common.reference_data.views import (
  ReferenceBanksView,
  ReferenceCitiesView,
  ReferenceCountriesView,
  ReferenceLgasView,
  ReferenceStateLgaCitiesView,
  ReferenceStatesView,
)

app_name = "common"  # matches namespace='common' in backend/urls.py

urlpatterns = [
  # ── Health Check ─────────────────────────────────────────────────────────
  # GET /api/v1/health/
  # Used by: AWS ELB, Render.com, Kubernetes probes, Uptime Robot
  # path("v1/health/", HealthCheckView.as_view(), name="health-check"),

  # ── Cloudinary Presign ────────────────────────────────────────────────────
  # POST /api/v1/upload/presign/ — Generates signed upload token (JWT required)
  path("v1/upload/presign/", CloudinaryPresignView.as_view(), name="cloudinary-presign"),

  # ── Cloudinary Webhook ────────────────────────────────────────────────────
  # POST /api/v1/upload/webhook/cloudinary/ — Cloudinary HMAC-SHA256 event receiver
  # CSRF-exempt, signature-validated, no user auth required
  path("v1/upload/webhook/cloudinary/", CloudinaryWebhookView.as_view(), name="cloudinary-webhook"),

  # ── Static Reference Data ─────────────────────────────────────────────────
  # GET /api/v1/common/reference/countries/
  path("v1/common/reference/countries/", ReferenceCountriesView.as_view(), name="reference-countries"),
  # GET /api/v1/common/reference/countries/NG/states/
  path(
    "v1/common/reference/countries/<str:country_code>/states/",
    ReferenceStatesView.as_view(),
    name="reference-country-states",
  ),
  # GET /api/v1/common/reference/countries/NG/states/LAGOS/lgas/
  path(
    "v1/common/reference/countries/<str:country_code>/states/<str:state_code>/lgas/",
    ReferenceLgasView.as_view(),
    name="reference-state-lgas",
  ),
  # GET /api/v1/common/reference/countries/NG/cities/?state=LAGOS&lga=IKEJA
  path(
    "v1/common/reference/countries/<str:country_code>/cities/",
    ReferenceCitiesView.as_view(),
    name="reference-country-cities",
  ),
  # GET /api/v1/common/reference/countries/NG/states/LAGOS/lgas/IKEJA/cities/
  path(
    "v1/common/reference/countries/<str:country_code>/states/<str:state_code>/lgas/<str:lga_code>/cities/",
    ReferenceStateLgaCitiesView.as_view(),
    name="reference-lga-cities",
  ),
  # GET /api/v1/common/reference/banks/?country=NG
  path("v1/common/reference/banks/", ReferenceBanksView.as_view(), name="reference-banks"),
]
