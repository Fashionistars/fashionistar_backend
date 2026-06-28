# apps/measurements/urls.py
from django.urls import path
from apps.measurements.apis.sync import (
    MeasurementProfileListCreateView,
    MeasurementProfileDetailView,
    SetDefaultProfileView,
)
from apps.measurements.apis.sync.scan_views import (
    InitiateScanView,
    SubmitLandmarksView,
)

app_name = "measurements"

urlpatterns = [
    # ── Profile CRUD ──────────────────────────────────────────────────────────
    path("", MeasurementProfileListCreateView.as_view(), name="profile-list-create"),
    path("<int:profile_id>/", MeasurementProfileDetailView.as_view(), name="profile-detail"),
    path("<int:profile_id>/set-default/", SetDefaultProfileView.as_view(), name="profile-set-default"),

    # ── AI Camera Scan ────────────────────────────────────────────────────────
    # POST /api/v1/measurements/scan/initiate/
    path("scan/initiate/", InitiateScanView.as_view(), name="scan-initiate"),
    # POST /api/v1/measurements/scan/<session_id>/submit-landmarks/
    path("scan/<str:session_id>/submit-landmarks/", SubmitLandmarksView.as_view(), name="scan-submit-landmarks"),
    # GET  /api/v1/ninja/measurements/scan/<session_id>/status/  ← Ninja async (see ninja_api.py)
]
