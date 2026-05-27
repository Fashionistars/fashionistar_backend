# apps/kyc/admin_backend/services.py
import logging
from uuid import UUID
from django.db import transaction
from apps.kyc.services.kyc_service import KycService
from apps.common.events import event_bus

logger = logging.getLogger(__name__)

class AdminKycService:
    @staticmethod
    @transaction.atomic
    def approve_kyc(submission_id: UUID, admin_user, provider_reference: str = ""):
        """
        Approve a KYC submission.
        """
        submission = KycService.approve_submission(
            submission_id=submission_id,
            admin_user=admin_user,
            provider_reference=provider_reference,
        )
        
        # Dispatch admin action event on transaction commit
        transaction.on_commit(
            lambda: event_bus.emit(
                "admin.kyc.approved",
                submission_id=str(submission_id),
                admin_id=str(admin_user.id) if admin_user else "system",
            )
        )
        return submission

    @staticmethod
    @transaction.atomic
    def reject_kyc(submission_id: UUID, admin_user, review_notes: str, allow_resubmit: bool = True):
        """
        Reject a KYC submission.
        """
        submission = KycService.reject_submission(
            submission_id=submission_id,
            admin_user=admin_user,
            review_notes=review_notes,
            allow_resubmit=allow_resubmit,
        )
        
        # Dispatch admin action event on transaction commit
        transaction.on_commit(
            lambda: event_bus.emit(
                "admin.kyc.rejected",
                submission_id=str(submission_id),
                admin_id=str(admin_user.id) if admin_user else "system",
                reason=review_notes,
            )
        )
        return submission
