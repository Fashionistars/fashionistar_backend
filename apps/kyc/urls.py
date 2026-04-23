# apps/kyc/urls.py
"""
KYC Domain URLs — SCAFFOLD (not yet mounted in backend/urls.py).

When activated, mount at: /api/v1/kyc/

Planned endpoints:
  POST /api/v1/kyc/submit/                   — initiate KYC submission
  POST /api/v1/kyc/documents/upload/         — upload a KYC document
  GET  /api/v1/kyc/status/                   — check own KYC status
  POST /api/v1/kyc/webhook/<provider>/       — receive provider webhook

Activation:
  1. Uncomment urlpatterns below
  2. Add to backend/urls.py: path("api/v1/kyc/", include("apps.kyc.urls", namespace="kyc"))
"""
from django.urls import path

# Uncomment after implementing views:
# from apps.kyc.apis.sync.submission_views import (
#     KycSubmitView,
#     KycDocumentUploadView,
#     KycStatusView,
# )

app_name = "kyc"

urlpatterns = [
    # Scaffold — no active routes yet.
    # path("submit/",              KycSubmitView.as_view(),          name="submit"),
    # path("documents/upload/",    KycDocumentUploadView.as_view(),  name="document-upload"),
    # path("status/",              KycStatusView.as_view(),          name="status"),
]
