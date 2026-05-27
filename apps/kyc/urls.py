# apps/kyc/urls.py
"""
KYC Domain URLs.

Mounted at: /api/v1/kyc/

Endpoints:
  GET  /api/v1/kyc/status/               — Check own KYC status + documents (sync)
  POST /api/v1/kyc/submit/               — Initiate / reopen KYC submission
  POST /api/v1/kyc/documents/upload/     — Record Cloudinary document upload
  POST /api/v1/kyc/admin/<id>/approve/   — Admin: approve a submission
  POST /api/v1/kyc/admin/<id>/reject/    — Admin: reject a submission
  POST /api/v1/kyc/webhook/<provider>/   — KYC provider webhook callback [NEW]

Async read endpoints are on the Ninja surface:
  GET  /api/v1/ninja/kyc/status/
  GET  /api/v1/ninja/kyc/documents/
"""
from django.urls import path

from apps.kyc.apis.sync.kyc_views import (
    KycStatusView,
    KycSubmitView,
    KycDocumentUploadView,
    KycApproveView,
    KycRejectView,
    KycAdminSubmissionListView,
)
from apps.kyc.apis.sync.kyc_webhook_view import KycWebhookView

app_name = "kyc"

urlpatterns = [
    # ── User-facing ────────────────────────────────────────────────────────────
    path("status/",              KycStatusView.as_view(),         name="status"),
    path("submit/",              KycSubmitView.as_view(),         name="submit"),
    path("documents/upload/",    KycDocumentUploadView.as_view(), name="document-upload"),

    # ── Admin review actions ───────────────────────────────────────────────────
    path(
        "admin/submissions/",
        KycAdminSubmissionListView.as_view(),
        name="admin-submissions-list",
    ),
    path(
        "admin/<uuid:submission_id>/approve/",
        KycApproveView.as_view(),
        name="admin-approve",
    ),
    path(
        "admin/<uuid:submission_id>/reject/",
        KycRejectView.as_view(),
        name="admin-reject",
    ),


    # ── KYC Provider Webhook Callbacks ─────────────────────────────────────────
    # POST /api/v1/kyc/webhook/smileid/
    # POST /api/v1/kyc/webhook/dojah/
    # POST /api/v1/kyc/webhook/youverify/
    path(
        "webhook/<str:provider_slug>/",
        KycWebhookView.as_view(),
        name="webhook",
    ),
]
