# apps/common/urls.py
from django.urls import path
from .views import HealthCheckView

app_name = "common"  # matches namespace='common' in backend/urls.py

urlpatterns = [
    # GET /api/health/
    # Used by: AWS ELB, Render.com, Kubernetes probes, Uptime Robot
    path("health/", HealthCheckView.as_view(), name="health-check"),
]
