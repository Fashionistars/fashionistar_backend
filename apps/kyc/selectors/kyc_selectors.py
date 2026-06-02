"""KYC Domain — read-only selectors.

User-scoped selectors traverse from ``request.user.kyc_submission``. Global
admin queues are intentionally absent here until a paginated staff review
surface is added.
"""

import asyncio
import logging
from typing import Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet

logger = logging.getLogger(__name__)


def get_kyc_submission_for_user(user) -> Optional["KycSubmission"]:  # noqa: F821
    """Return the KYC submission for ``user`` or None.

    Traversal:
        ``request.user.kyc_submission`` -> KycSubmission (OneToOne).

    Notes:
        If the relation was not preloaded, Django may issue a single scoped
        SELECT for this user's row. No global ``KycSubmission.objects`` lookup
        is performed by endpoint code.
    """
    try:
        submission = user.kyc_submission
    except ObjectDoesNotExist:
        return None
    return submission


def get_kyc_documents_for_submission(submission) -> QuerySet:
    """Return documents for an already user-scoped submission.

    Traversal:
        ``request.user.kyc_submission.documents`` -> KycDocument rows.
    """
    return submission.documents.order_by("created_at")


async def aget_kyc_submission_for_user(user) -> Optional["KycSubmission"]:  # noqa: F821
    """Async fetch of a KYC submission through a scoped native ORM query.

    The query is scoped to ``request.auth`` via ``user_id`` and uses
    ``afirst()`` so Ninja read routes never trigger a sync reverse-relation
    lookup inside the event loop.
    """
    from apps.kyc.models import KycSubmission

    return await KycSubmission.objects.filter(user_id=user.id).afirst()


async def aget_kyc_documents_for_submission(submission) -> list:
    """Async list of documents through ``submission.documents``."""
    return [doc async for doc in submission.documents.order_by("created_at")]


def build_kyc_status_summary(submission, document_count: int = 0) -> dict:
    """Serialize a KYC status summary for sync and async readers."""
    if submission is None:
        return {
            "id": None,
            "status": "not_started",
            "is_approved": False,
            "is_pending": False,
            "document_count": 0,
            "submitted_at": None,
            "reviewed_at": None,
            "review_notes": "",
            "provider_reference": "",
            "can_withdraw": False,
        }
    return {
        "id": str(submission.id),
        "status": submission.status,
        "is_approved": submission.is_approved,
        "is_pending": submission.is_pending,
        "document_count": document_count,
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        "reviewed_at": submission.reviewed_at.isoformat() if submission.reviewed_at else None,
        "review_notes": submission.review_notes,
        "provider_reference": submission.provider_reference,
        "can_withdraw": submission.is_approved,
    }


async def aget_kyc_status_summary(user) -> dict:
    """Async status summary using reverse OneToOne + reverse document manager."""
    submission = await aget_kyc_submission_for_user(user)
    if submission is None:
        return build_kyc_status_summary(None)
    document_count = await submission.documents.acount()
    return build_kyc_status_summary(submission, document_count=document_count)


async def aget_kyc_with_documents(user) -> dict:
    """Async full KYC status with submitted documents."""
    submission = await aget_kyc_submission_for_user(user)
    if submission is None:
        return {**build_kyc_status_summary(None), "documents": []}
    count_task = submission.documents.acount()
    docs_task = aget_kyc_documents_for_submission(submission)
    document_count, documents = await asyncio.gather(count_task, docs_task)
    return {
        **build_kyc_status_summary(submission, document_count=document_count),
        "documents": [
            {
                "id": str(doc.id),
                "document_type": doc.document_type,
                "secure_url": doc.secure_url,
                "public_id": doc.public_id,
                "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in documents
        ],
    }
