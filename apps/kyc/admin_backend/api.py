# apps/kyc/admin_backend/api.py
"""
Django Ninja async API for KYC admin domain.

GET endpoints are async. Approve/reject are exposed as Ninja async PATCH
fast-paths (permitted async exceptions per architecture rules).
"""
from __future__ import annotations
import logging
from typing import Optional
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from .selectors import list_kyc_submissions_admin, get_kyc_detail_admin, get_kyc_stats_admin
from .schemas import AdminKYCStatsSchema, AdminKYCApproveSchema, AdminKYCRejectSchema, AdminKYCActionResponse
from .services import AdminKYCService

logger = logging.getLogger(__name__)
router = Router(tags=["Admin - KYC"])


@router.get("/", summary="Admin: List KYC Submissions", auth=admin_auth)
async def admin_list_kyc(
    request,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    ordering: str = "-submitted_at",
    page: int = 1,
    page_size: int = 25,
):
    return await list_kyc_submissions_admin(
        status=status, user_id=user_id, search=search,
        ordering=ordering, page=page, page_size=page_size,
    )


@router.get("/stats/", response=AdminKYCStatsSchema, summary="Admin: KYC KPI Stats", auth=admin_auth)
async def admin_kyc_stats(request):
    return await get_kyc_stats_admin()


@router.get("/{submission_id}/", summary="Admin: KYC Detail", auth=admin_auth)
async def admin_kyc_detail(request, submission_id: str):
    from apps.kyc.models import KycSubmission
    try:
        submission = await get_kyc_detail_admin(submission_id=submission_id)
    except KycSubmission.DoesNotExist:
        return {"success": False, "message": "KYC submission not found."}
    return {
        "id": str(submission.pk),
        "user_id": str(submission.user_id),
        "user_email": getattr(submission.user, "email", None),
        "status": submission.status,
        "legal_name": submission.legal_name,
        "review_notes": submission.review_notes,
        "provider_reference": submission.provider_reference,
        "submitted_at": submission.submitted_at.isoformat(),
        "reviewed_at": submission.reviewed_at.isoformat() if submission.reviewed_at else None,
    }


# ── Async PATCH exceptions (permitted per architecture rules) ──────────────

@router.patch("/{submission_id}/approve/", response=AdminKYCActionResponse, summary="Admin: Quick Approve KYC", auth=admin_auth)
async def admin_kyc_quick_approve(request, submission_id: str, payload: AdminKYCApproveSchema):
    """
    Async PATCH fast-path for KYC approval.
    Allowed as async exception: no complex post-commit financial side effects.
    Wraps sync service in sync_to_async for transaction safety.
    """
    from asgiref.sync import sync_to_async
    try:
        approve_fn = sync_to_async(AdminKYCService.approve_kyc, thread_sensitive=True)
        submission = await approve_fn(
            submission_id=submission_id,
            legal_name=payload.legal_name or "",
            admin_user=request.auth,
        )
    except Exception as exc:
        return AdminKYCActionResponse(success=False, message=str(exc))
    return AdminKYCActionResponse(
        success=True,
        message="KYC approved successfully.",
        submission_id=str(submission.pk),
    )


@router.patch("/{submission_id}/reject/", response=AdminKYCActionResponse, summary="Admin: Quick Reject KYC", auth=admin_auth)
async def admin_kyc_quick_reject(request, submission_id: str, payload: AdminKYCRejectSchema):
    """Async PATCH fast-path for KYC rejection."""
    from asgiref.sync import sync_to_async
    try:
        reject_fn = sync_to_async(AdminKYCService.reject_kyc, thread_sensitive=True)
        submission = await reject_fn(
            submission_id=submission_id,
            notes=payload.notes,
            allow_resubmit=payload.allow_resubmit,
            admin_user=request.auth,
        )
    except Exception as exc:
        return AdminKYCActionResponse(success=False, message=str(exc))
    return AdminKYCActionResponse(
        success=True,
        message="KYC rejected successfully.",
        submission_id=str(submission.pk),
    )
