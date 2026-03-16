# apps/common/urls.py
from django.urls import path
from .views import HealthCheckView, CloudinaryPresignView, CloudinaryWebhookView

app_name = "common"  # matches namespace='common' in backend/urls.py

urlpatterns = [
    # GET /api/health/
    # Used by: AWS ELB, Render.com, Kubernetes probes, Uptime Robot
    path("health/", HealthCheckView.as_view(), name="health-check"),

    # POST /api/v1/upload/presign/ — Cloudinary presign token (JWT required)
    path("upload/presign/", CloudinaryPresignView.as_view(), name="cloudinary-presign"),

    # POST /api/v1/upload/webhook/cloudinary/ — Cloudinary notification receiver
    # CSRF-exempt, HMAC-SHA256 validated, no user auth required
    path("upload/webhook/cloudinary/", CloudinaryWebhookView.as_view(), name="cloudinary-webhook"),
]
