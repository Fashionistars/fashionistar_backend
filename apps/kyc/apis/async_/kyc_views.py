# apps/kyc/apis/async_/kyc_views.py
"""
KYC Domain — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/kyc/

Architecture:
  ─ All endpoints are READ-ONLY.
  ─ KYC submission mutations live on the DRF sync surface (/api/v1/kyc/).
  ─ Each handler delegates to KYC selectors.
  ─ Zero sync_to_async: Django 6.0 native async ORM only.

Endpoints:
  GET /api/v1/ninja/kyc/status/         — KYC status summary + document count
  GET /api/v1/ninja/kyc/documents/      — Full submission + all documents
"""
import logging

from ninja import Router
from ninja.errors import HttpError

from apps.kyc.selectors import aget_kyc_status_summary, aget_kyc_with_documents

logger = logging.getLogger(__name__)

router = Router(tags=["KYC — Async Status"])


def _get_auth_user(request):
    """Extract the authenticated user from the Ninja request."""
    return request.auth.user if hasattr(request.auth, "user") else request.auth


# ── Status Summary ─────────────────────────────────────────────────────────────


@router.get("/status/")
async def get_kyc_status(request):
    """
    GET /api/v1/ninja/kyc/status/

    KYC status summary in 2 DB queries:
    1. Fetch submission record (afirst)
    2. acount() on related documents

    Response shape:
        {
          "id": "uuid" | None,
          "status": "pending" | "in_review" | "approved" | "rejected" | "resubmit" | "not_started",
          "is_approved": bool,
          "is_pending": bool,
          "document_count": int,
          "submitted_at": "iso8601" | None,
          "reviewed_at": "iso8601" | None,
          "review_notes": str,
          "provider_reference": str
        }
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        summary = await aget_kyc_status_summary(user)
        return {"status": "success", "data": summary}
    except Exception:
        logger.exception(
            "get_kyc_status: unexpected error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "KYC status fetch failed.")


# ── Submission + Documents ─────────────────────────────────────────────────────


@router.get("/documents/")
async def get_kyc_documents(request):
    """
    GET /api/v1/ninja/kyc/documents/

    Full KYC submission with all submitted document records.
    Uses async iteration over submission.documents reverse manager.

    Response shape:
        {
          "id": "uuid" | None,
          "status": str,
          "is_approved": bool,
          "review_notes": str,
          "provider_reference": str,
          "submitted_at": "iso8601" | None,
          "reviewed_at": "iso8601" | None,
          "documents": [
            { "id": "uuid", "document_type": str, "secure_url": str, "uploaded_at": "iso8601" }
          ]
        }
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        submission_data = await aget_kyc_with_documents(user)
        return {"status": "success", "data": submission_data}
    except Exception:
        logger.exception(
            "get_kyc_documents: unexpected error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "KYC documents fetch failed.")
