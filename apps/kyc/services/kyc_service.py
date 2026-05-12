# apps/kyc/services/kyc_service.py
"""
KYC Domain — Service Layer.

Architecture:
  ─ ALL write operations use transaction.atomic().
  ─ Services are sync and are called from DRF mutation endpoints.
  ─ Ninja endpoints stay read-only and use native async selectors.
  ─ KycGateError is raised when a user attempts a withdrawal without
    an approved KYC submission (the KYC Gate).

KYC Gate:
  The `assert_kyc_approved(user)` function must be called by the wallet/
  transaction service before any withdrawal is processed. This is the
  canonical enforcement point for the KYC gate across all fund exit paths.

Nigerian KYC Standards:
  - Vendors: NIN (National Identification Number) + CAC certificate required.
  - Clients: NIN recommended for high-value transactions (>₦100,000).
  - Supported document types: NIN card, BVN slip, international passport,
    driver's license, CAC certificate, utility bill.

External Provider:
  The external verification provider is configured via KYC_PROVIDER and
  KYC_API_KEY in .env (e.g., Dojah, Smile Identity, Youverify).
  This service layer provides the integration scaffold — plug in the
  actual provider SDK when credentials are available.
"""
import hashlib
import logging
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.kyc.selectors import get_kyc_submission_for_user

User = get_user_model()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# KYC GATE EXCEPTION
# ─────────────────────────────────────────────────────────────────────────────


class KycGateError(Exception):
    """
    Raised when a user attempts a privileged financial action (withdrawal)
    without an approved KYC submission.

    The HTTP layer maps this to HTTP 403 Forbidden with a clear message
    guiding the user to complete KYC verification.
    """


# ─────────────────────────────────────────────────────────────────────────────
# KYC GATE (called by wallet / transaction withdrawal services)
# ─────────────────────────────────────────────────────────────────────────────


def assert_kyc_approved(user) -> None:
    """
    Enforce the KYC gate for fund withdrawal operations.

    This function MUST be called at the start of any withdrawal flow
    (vendor payouts, client refund requests, wallet transfers).

    Raises:
        KycGateError: If the user does not have an approved KYC submission.

    Usage (in wallet/transaction service):
        from apps.kyc.services import assert_kyc_approved, KycGateError

        try:
            assert_kyc_approved(user)
        except KycGateError as e:
            raise WithdrawalError(str(e))
    """
    from apps.kyc.models.kyc_submission import KycStatus

    # Reverse OneToOne traversal: request.user.kyc_submission is the canonical
    # identity verification relationship. Fund-exit gates must never perform an
    # unscoped KYC table lookup before money leaves a wallet.
    submission = get_kyc_submission_for_user(user)

    if submission is None:
        raise KycGateError(
            "Identity verification required before withdrawals. "
            "Please complete your KYC verification in Account → Verify Identity."
        )

    if submission.status != KycStatus.APPROVED:
        status_messages = {
            KycStatus.PENDING: (
                "Your KYC verification is pending review. "
                "Withdrawals will be enabled once your identity is verified."
            ),
            KycStatus.IN_REVIEW: (
                "Your identity documents are currently under review. "
                "Withdrawals will be enabled within 24-48 hours."
            ),
            KycStatus.REJECTED: (
                "Your KYC submission was rejected. "
                "Please resubmit with valid identity documents."
            ),
            KycStatus.RESUBMIT: (
                "Additional documents are required for identity verification. "
                "Please check the review notes and resubmit."
            ),
        }
        message = status_messages.get(
            submission.status,
            "Identity verification incomplete. Please complete KYC before withdrawing funds."
        )
        raise KycGateError(message)


async def aassert_kyc_approved(user) -> None:
    """
    Async version of the KYC gate for use in Ninja async views.
    Uses Django 6.0 native async ORM (afirst).

    Raises:
        KycGateError: If the user does not have an approved KYC submission.
    """
    from apps.kyc.models.kyc_submission import KycStatus
    from apps.kyc.selectors import aget_kyc_submission_for_user

    submission = await aget_kyc_submission_for_user(user)

    if submission is None:
        raise KycGateError(
            "Identity verification required before withdrawals. "
            "Please complete your KYC verification in Account → Verify Identity."
        )

    if submission.status != KycStatus.APPROVED:
        raise KycGateError(
            f"KYC status is '{submission.status}'. "
            "Withdrawals are only permitted after identity verification is approved."
        )


# ─────────────────────────────────────────────────────────────────────────────
# KYC SERVICE CLASS
# ─────────────────────────────────────────────────────────────────────────────


class KycService:
    """
    Central service for KYC submission lifecycle management.

    All class methods are sync and wrapped in transaction.atomic(). Keep them
    on the DRF mutation surface so Ninja read routes remain native async only.
    """

    # ── Submission Initiation ─────────────────────────────────────────────────

    @staticmethod
    def _hash_identifier(value: str) -> str:
        """Hash BVN/NIN values before storage.

        Raw BVN/NIN must not be persisted in plaintext. The salted hash supports
        provider correlation and duplicate checks without exposing regulated
        identity numbers in application rows.
        """
        cleaned = "".join(ch for ch in value if ch.isalnum())
        if not cleaned:
            return ""
        salt = settings.SECRET_KEY.encode("utf-8")
        return hashlib.sha256(salt + cleaned.encode("utf-8")).hexdigest()

    @staticmethod
    def _last4(value: str) -> str:
        """Return only the last four characters of an identity number."""
        cleaned = "".join(ch for ch in value if ch.isalnum())
        return cleaned[-4:] if cleaned else ""

    @staticmethod
    @transaction.atomic
    def initiate_submission(user, nin: str = "", bvn: str = "") -> "KycSubmission":  # noqa: F821
        """
        Initiate or reopen a KYC submission for the given user.

        Idempotent per user: returns the existing submission if one exists
        and is not in REJECTED or RESUBMIT state. A REJECTED submission
        is reset to PENDING for resubmission.

        Args:
            user: The UnifiedUser initiating KYC.
            nin: Optional Nigerian NIN.
            bvn: Optional BVN.

        Returns:
            KycSubmission instance.
        """
        from apps.kyc.models.kyc_submission import KycSubmission, KycStatus
        from django.utils import timezone

        existing = KycSubmission.objects.select_for_update().filter(user=user).first()

        if existing:
            if existing.status in (KycStatus.REJECTED, KycStatus.RESUBMIT):
                # Reset for resubmission
                existing.status = KycStatus.PENDING
                existing.review_notes = ""
                existing.submitted_at = timezone.now()
                existing.reviewed_at = None
                existing.save(update_fields=[
                    "status", "review_notes", "submitted_at", "reviewed_at", "updated_at"
                ])
                logger.info(
                    "KycService.initiate_submission: reset submission=%s for user=%s",
                    existing.id, user.id,
                )
            return existing

        # Create new submission
        submission = KycSubmission.objects.create(
            user=user,
            status=KycStatus.PENDING,
        )

        # Store only salted hashes and last-four markers. Raw BVN/NIN numbers
        # are never persisted in provider_reference.
        if nin or bvn:
            parts = []
            if nin:
                parts.append(f"nin_hash={KycService._hash_identifier(nin)};nin_last4={KycService._last4(nin)}")
            if bvn:
                parts.append(f"bvn_hash={KycService._hash_identifier(bvn)};bvn_last4={KycService._last4(bvn)}")
            submission.provider_reference = "|".join(parts)
            submission.save(update_fields=["provider_reference", "updated_at"])

        logger.info(
            "KycService.initiate_submission: created submission=%s for user=%s",
            submission.id, user.id,
        )
        # Compliance audit trail
        try:
            from apps.audit_logs.services.audit import AuditService
            from apps.audit_logs.models import EventType, EventCategory, SeverityLevel
            AuditService.log(
                event_type=EventType.KYC_SUBMITTED,
                event_category=EventCategory.COMPLIANCE,
                severity=SeverityLevel.INFO,
                action=f"KYC submission initiated for user={user.id}",
                actor=user,
                actor_role=getattr(user, 'role', None),
                resource_type="KycSubmission",
                resource_id=str(submission.id),
                new_values={"status": "PENDING", "has_nin": bool(nin), "has_bvn": bool(bvn)},
                is_compliance=True,
                retention_days=2555,  # 7 years NDPR/CBN
            )
        except Exception:
            pass
        return submission

    # ── Document Upload Recording ─────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def record_document(
        user,
        document_type: str,
        secure_url: str,
        public_id: str,
        document_number: str = "",
    ) -> "KycDocument":  # noqa: F821
        """
        Record a KYC document upload against the user's active submission.

        The document file has already been uploaded to Cloudinary by the client.
        This method records the Cloudinary asset reference against the submission.

        Idempotent per (submission, document_type): updates the existing document
        record if the user resubmits the same document type.

        Args:
            user: The UnifiedUser uploading the document.
            document_type: One of KycDocumentType choices.
            secure_url: Cloudinary secure URL of the uploaded document.
            public_id: Cloudinary public_id of the uploaded document.
            document_number: Optional document number / ID string.

        Returns:
            KycDocument instance.

        Raises:
            ValueError: If the user has no active KYC submission to attach to.
        """
        from apps.kyc.models.kyc_submission import KycSubmission, KycStatus
        from apps.kyc.models.kyc_document import KycDocument

        submission = KycSubmission.objects.select_for_update().filter(
            user=user
        ).first()

        if submission is None:
            raise ValueError(
                "No active KYC submission found. Please initiate KYC before uploading documents."
            )

        if submission.status == KycStatus.APPROVED:
            raise ValueError(
                "Your identity is already verified. No document uploads required."
            )

        doc, created = KycDocument.objects.update_or_create(
            submission=submission,
            document_type=document_type,
            defaults={
                "secure_url": secure_url,
                "public_id": public_id,
                # Keep only the final four characters locally. Provider-grade
                # verification should use an encrypted vault or provider token.
                "document_number": KycService._last4(document_number),
                "provider_verified": False,
                "provider_response": {},
            },
        )

        logger.info(
            "KycService.record_document: %s doc=%s type=%s for user=%s",
            "created" if created else "updated",
            doc.id,
            document_type,
            user.id,
        )
        # Compliance audit trail
        try:
            from apps.audit_logs.services.audit import AuditService
            from apps.audit_logs.models import EventType, EventCategory, SeverityLevel
            AuditService.log(
                event_type=EventType.KYC_DOCUMENT_UPLOADED,
                event_category=EventCategory.COMPLIANCE,
                severity=SeverityLevel.INFO,
                action=f"KYC document {'created' if created else 'updated'}: type={document_type} for user={user.id}",
                actor=user,
                actor_role=getattr(user, 'role', None),
                resource_type="KycDocument",
                resource_id=str(doc.id),
                new_values={"document_type": document_type, "submission_id": str(submission.id), "created": created},
                is_compliance=True,
                retention_days=2555,
            )
        except Exception:
            pass

        if document_number and document_type in ("bvn_slip", "nin_card"):
            # Provider I/O must happen after the KYC document row commits so
            # callbacks and retries never observe a half-written submission.
            transaction.on_commit(
                lambda: KycService.dispatch_provider_verification(
                    submission=submission,
                    document_type=document_type,
                    document_number=document_number,
                )
            )

        # Notify after commit for the same reason as provider verification.
        transaction.on_commit(
            lambda: KycService._notify_document_uploaded(submission, doc, user)
        )

        return doc

    # ── Admin Review Actions ──────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def approve_submission(submission_id: UUID, admin_user, provider_reference: str = "") -> "KycSubmission":  # noqa: F821
        """
        Admin action: approve a KYC submission and update VendorSetupState.

        Side effects:
          - Sets submission.status = APPROVED.
          - Sets vendor.setup_state.id_verified = True if user is a vendor.
          - Dispatches approval notification.

        Args:
            submission_id: UUID of the KycSubmission.
            admin_user: Staff UnifiedUser performing the approval.
            provider_reference: Optional external provider reference ID.

        Returns:
            The approved KycSubmission.
        """
        from apps.kyc.models.kyc_submission import KycSubmission, KycStatus
        from django.utils import timezone

        if admin_user is not None and not getattr(admin_user, "is_staff", False):
            raise PermissionError("Only staff can approve KYC submissions.")

        submission = KycSubmission.objects.select_for_update().get(id=submission_id)
        submission.mark_approved(
            admin_user=admin_user,
            provider_reference=provider_reference,
        )

        # Update vendor setup state if user is a vendor
        KycService._sync_vendor_kyc_state(submission.user, approved=True)

        logger.info(
            "KycService.approve_submission: approved submission=%s by admin=%s",
            submission_id, getattr(admin_user, "id", "provider-webhook"),
        )
        # Compliance audit trail — permanent for CBN
        try:
            from apps.audit_logs.services.audit import AuditService
            from apps.audit_logs.models import EventType, EventCategory, SeverityLevel
            AuditService.log(
                event_type=EventType.KYC_APPROVED,
                event_category=EventCategory.COMPLIANCE,
                severity=SeverityLevel.INFO,
                action=f"KYC approved: submission={submission_id} admin={getattr(admin_user, 'id', 'webhook')}",
                actor=admin_user,
                actor_role="staff" if admin_user else "provider-webhook",
                resource_type="KycSubmission",
                resource_id=str(submission_id),
                new_values={"status": "APPROVED", "provider_reference": provider_reference},
                is_compliance=True,
                retention_days=-1,  # Permanent — financial compliance
            )
        except Exception:
            pass
        KycService._notify_kyc_approved(submission)
        return submission

    @staticmethod
    @transaction.atomic
    def reject_submission(
        submission_id: UUID,
        admin_user,
        review_notes: str,
        allow_resubmit: bool = True,
    ) -> "KycSubmission":  # noqa: F821
        """
        Admin action: reject a KYC submission with review notes.

        Args:
            submission_id: UUID of the KycSubmission.
            admin_user: Staff UnifiedUser performing the rejection.
            review_notes: Reason for rejection (shown to the user).
            allow_resubmit: If True, status becomes RESUBMIT; otherwise REJECTED.

        Returns:
            The rejected KycSubmission.
        """
        from apps.kyc.models.kyc_submission import KycSubmission, KycStatus
        from django.utils import timezone

        if admin_user is not None and not getattr(admin_user, "is_staff", False):
            raise PermissionError("Only staff can reject KYC submissions.")

        submission = KycSubmission.objects.select_for_update().get(id=submission_id)
        submission.mark_rejected(
            admin_user=admin_user,
            notes=review_notes,
            allow_resubmit=allow_resubmit,
        )

        logger.info(
            "KycService.reject_submission: rejected submission=%s by admin=%s",
            submission_id, getattr(admin_user, "id", "provider-webhook"),
        )
        # Compliance audit trail
        try:
            from apps.audit_logs.services.audit import AuditService
            from apps.audit_logs.models import EventType, EventCategory, SeverityLevel
            AuditService.log(
                event_type=EventType.KYC_REJECTED,
                event_category=EventCategory.COMPLIANCE,
                severity=SeverityLevel.WARNING,
                action=f"KYC rejected: submission={submission_id} admin={getattr(admin_user, 'id', 'webhook')} allow_resubmit={allow_resubmit}",
                actor=admin_user,
                actor_role="staff" if admin_user else "provider-webhook",
                resource_type="KycSubmission",
                resource_id=str(submission_id),
                new_values={"status": "RESUBMIT" if allow_resubmit else "REJECTED", "review_notes": review_notes[:500]},
                is_compliance=True,
                retention_days=2555,
            )
        except Exception:
            pass
        KycService._notify_kyc_rejected(submission)
        return submission

    # ── Internal Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _sync_vendor_kyc_state(user, *, approved: bool) -> None:
        """Update VendorSetupState.id_verified when KYC is approved/rejected."""
        try:
            # Cross-domain reverse traversal:
            # request.user.vendor_profile -> vendor_profile.vendor_setup_state.
            # No vendor setup model import is needed for the KYC service to mark
            # identity readiness after approval.
            vendor = getattr(user, "vendor_profile", None)
            state = getattr(vendor, "vendor_setup_state", None) if vendor else None
            if state:
                state.id_verified = approved
                state.save(update_fields=["id_verified", "updated_at"])
                logger.info(
                    "KycService._sync_vendor_kyc_state: vendor id_verified=%s for user=%s",
                    approved, user.id,
                )
        except Exception:
            logger.warning(
                "KycService._sync_vendor_kyc_state: failed for user=%s", user.id
            )

    @staticmethod
    def _notify_document_uploaded(submission, doc, user) -> None:
        """Fire-and-forget: notify staff of a new KYC document upload."""
        try:
            from apps.notification.services import send_notification
            send_notification(
                user=user,
                notification_type="system_alert",
                title="KYC document uploaded",
                body=(
                    f"Your {doc.get_document_type_display()} has been uploaded "
                    "and is pending review. Verification takes 24-48 hours."
                ),
                metadata={
                    "submission_id": str(submission.id),
                    "document_type": doc.document_type,
                },
            )
        except Exception:
            logger.warning(
                "KycService._notify_document_uploaded: notification failed for submission=%s",
                submission.id,
            )

    @staticmethod
    def _notify_kyc_approved(submission) -> None:
        """Fire-and-forget: notify user of KYC approval."""
        try:
            from apps.notification.services import send_notification
            send_notification(
                user=submission.user,
                notification_type="system_alert",
                title="Identity verified ✓",
                body=(
                    "Congratulations! Your identity has been verified. "
                    "You can now make withdrawals and access all platform features."
                ),
                metadata={"submission_id": str(submission.id)},
            )
        except Exception:
            logger.warning(
                "KycService._notify_kyc_approved: notification failed for submission=%s",
                submission.id,
            )

    @staticmethod
    def _notify_kyc_rejected(submission) -> None:
        """Fire-and-forget: notify user of KYC rejection."""
        try:
            from apps.notification.services import send_notification
            send_notification(
                user=submission.user,
                notification_type="system_alert",
                title="Identity verification failed",
                body=(
                    f"Your KYC submission requires attention. "
                    f"Reason: {submission.review_notes[:120]}. "
                    "Please re-upload valid documents."
                ),
                metadata={"submission_id": str(submission.id)},
            )
        except Exception:
            logger.warning(
                "KycService._notify_kyc_rejected: notification failed for submission=%s",
                submission.id,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # PROVIDER DISPATCH  (Phase 7: Unified Provider Registry)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def dispatch_provider_verification(
        submission,
        document_type: str,
        document_number: str,
    ) -> None:
        """
        Dispatch identity verification to the active KYC provider.
        NDPR: raw document_number is never stored — only hash + last4 used.
        """
        from apps.providers.KYC import load_kyc_provider
        from apps.providers.cache import get_kyc_provider_config
        from apps.providers.circuit_breaker import CircuitBreaker

        try:
            config = get_kyc_provider_config()
            provider = load_kyc_provider(config)
        except Exception as exc:
            logger.error("KycService.dispatch_provider_verification: provider load failed — %s", exc)
            return

        cleaned = "".join(ch for ch in document_number if ch.isalnum())
        last4 = cleaned[-4:] if len(cleaned) >= 4 else cleaned
        number_hash = KycService._hash_identifier(cleaned)
        cb = CircuitBreaker("kyc")
        result = None
        try:
            if document_type == "bvn_slip":
                result = provider.verify_bvn(number_hash, last4)
            elif document_type in ("nin_card", "nin_slip"):
                result = provider.verify_nin(number_hash, last4)
            else:
                return
            if result.success:
                cb.record_success()
            else:
                cb.record_failure(RuntimeError(result.error_message or result.error_code or "KYC provider verification failed"))
        except Exception as exc:
            cb.record_failure(exc)
            logger.error("KycService.dispatch_provider_verification: provider error — %s", exc)
            return

        if result is None:
            return

        try:
            from apps.kyc.models import KycDocument
            KycDocument.objects.filter(submission=submission, document_type=document_type).update(
                provider_verified=result.success,
                provider_response={
                    "provider": config.provider_slug,
                    "provider_reference": result.provider_reference,
                    "confidence_score": result.confidence_score,
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                    "raw_response": result.raw_response,
                },
            )
            # Sandbox providers use masked identifiers for contract testing.
            # Record the response, but require live-mode provider verification
            # before automatically approving a user's KYC submission.
            if result.success and result.provider_reference and not config.sandbox_mode:
                KycService.approve_submission(
                    submission_id=submission.id,
                    admin_user=None,
                    provider_reference=result.provider_reference,
                )
            logger.info(
                "KycService.dispatch_provider_verification: done submission=%s type=%s success=%s",
                submission.id, document_type, result.success,
            )
        except Exception as exc:
            logger.error("KycService.dispatch_provider_verification: DB update failed — %s", exc)

    @staticmethod
    def reconcile_webhook(provider_reference: str, success: bool, raw_payload: dict) -> None:
        """
        Reconcile an inbound KYC provider webhook callback. Idempotent.
        Auto-approves submission when provider confirms identity verified.
        """
        from apps.kyc.models import KycDocument
        try:
            doc = KycDocument.objects.filter(
                provider_response__provider_reference=provider_reference
            ).select_related("submission").first()
            if doc is None:
                logger.warning("KycService.reconcile_webhook: no document for ref=%s", provider_reference)
                return
            existing = doc.provider_response or {}
            if existing.get("webhook_reconciled"):
                return
            with transaction.atomic():
                doc.provider_verified = success
                existing["webhook_reconciled"] = True
                existing["webhook_payload"] = raw_payload
                doc.provider_response = existing
                doc.save(update_fields=["provider_verified", "provider_response", "updated_at"])
                if success:
                    KycService.approve_submission(
                        submission_id=doc.submission_id,
                        admin_user=None,
                        provider_reference=provider_reference,
                    )
                    logger.info("KycService.reconcile_webhook: auto-approved submission=%s", doc.submission_id)
        except Exception as exc:
            logger.error("KycService.reconcile_webhook: error for ref=%s — %s", provider_reference, exc)
