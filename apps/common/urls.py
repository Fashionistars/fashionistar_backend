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
# from apps.common.views import HealthCheckView, CloudinaryPresignView, CloudinaryWebhookView

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
]
