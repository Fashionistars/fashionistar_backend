# apps/kyc/admin_backend/selectors.py
"""Async selectors for KYC admin domain. Anchor: KycSubmission."""
from __future__ import annotations
import logging
from typing import Optional
from django.db.models import QuerySet

logger = logging.getLogger(__name__)


def get_kyc_submissions_admin_qs(
    *,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    ordering: str = "-submitted_at",
) -> QuerySet:
    from apps.kyc.models import KycSubmission
    qs = (
        KycSubmission.objects.select_related("user")
        .prefetch_related("documents")
    )
    if status:
        qs = qs.filter(status=status)
    if user_id:
        qs = qs.filter(user_id=user_id)
    if search:
        qs = qs.filter(user__email__icontains=search) | qs.filter(
            legal_name__icontains=search
        )
    return qs.order_by(ordering)


async def list_kyc_submissions_admin(
    *,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    ordering: str = "-submitted_at",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    from apps.common.pagination import async_ninja_paginate
    qs = get_kyc_submissions_admin_qs(
        status=status, user_id=user_id, search=search, ordering=ordering
    )
    return await async_ninja_paginate(None, qs, page=page, page_size=page_size)


async def get_kyc_detail_admin(*, submission_id: str):
    from apps.kyc.models import KycSubmission
    return await (
        KycSubmission.objects.select_related("user")
        .prefetch_related("documents")
        .aget(pk=submission_id)
    )


async def get_kyc_stats_admin() -> dict:
    from apps.kyc.models import KycSubmission, KycStatus
    from django.utils import timezone
    today = timezone.now().date()

    pending = await KycSubmission.objects.filter(status=KycStatus.PENDING).acount()
    in_review = await KycSubmission.objects.filter(status=KycStatus.IN_REVIEW).acount()
    approved = await KycSubmission.objects.filter(status=KycStatus.APPROVED).acount()
    rejected = await KycSubmission.objects.filter(
        status__in=[KycStatus.REJECTED, KycStatus.RESUBMIT]
    ).acount()
    new_today = await KycSubmission.objects.filter(submitted_at__date=today).acount()

    return {
        "pending": pending,
        "in_review": in_review,
        "approved": approved,
        "rejected": rejected,
        "new_today": new_today,
        "total": pending + in_review + approved + rejected,
    }
