"""KYC domain audit helper — Wave B6 (enhanced with KycAuditService class)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)

_KYC_RETENTION_DAYS = 2555  # 7 years (NDPR / financial services compliance)


class KycAuditService:
    """
    Class-based facade for KYC compliance audit events.

    All methods delegate to module-level helpers (backwards-compatible).
    Used by KycWebhookView for webhook outcome auditing.
    """

    @staticmethod
    def log_webhook_event(
        *,
        event_type: str,
        request: "HttpRequest",
        provider_slug: str,
        provider_reference: str,
        success: bool,
        metadata: dict | None = None,
    ) -> None:
        """Log a KYC provider webhook callback outcome to AuditEventLog."""
        log_kyc_webhook(
            submission_id=provider_reference or "",
            provider=provider_slug,
            event=event_type,
            metadata={
                "success": success,
                "provider_reference": provider_reference,
                **(metadata or {}),
            },
        )

    @staticmethod
    def log_kyc_approved(
        *,
        submission_id: str,
        actor,
        user,
        provider_reference: str = "",
        actor_email: str,
        request: "HttpRequest | None" = None,
    ) -> None:
        """Log admin manually approved a KYC submission."""
        log_kyc_approved(
            actor=actor,
            user=user or type("_u", (), {"email": actor_email})(),
            submission_id=submission_id,
            provider_reference=provider_reference,
            request=request,
        )

    @staticmethod
    def log_kyc_submitted_event(
        *,
        actor,
        submission_id: str,
        request: "HttpRequest | None" = None,
        metadata: dict | None = None,
    ) -> None:
        """Log KYC documents submitted by a user."""
        log_kyc_submitted(
            actor=actor,
            submission_id=submission_id,
            request=request,
            metadata=metadata,
        )

    @staticmethod
    def log_kyc_document_uploaded(
        *,
        actor,
        submission_id: str,
        document_id: str,
        document_type: str,
        created: bool,
        request: "HttpRequest | None" = None,
    ) -> None:
        log_kyc_document_uploaded(
            actor=actor,
            submission_id=submission_id,
            document_id=document_id,
            document_type=document_type,
            created=created,
            request=request,
        )



def log_kyc_submitted(*, actor, submission_id: str, request=None, metadata: dict | None = None) -> None:
    """Record a KYC submission.

    Args:
        actor: The user submitting KYC documents.
        submission_id: KYCSubmission PK.
        request: Django HttpRequest.
        metadata: Document types submitted, etc.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.KYC_SUBMITTED,
        event_category=EventCategory.KYC,
        action=f"KYC documents submitted: submission={submission_id}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="KYCSubmission",
        resource_id=submission_id,
        request=request,
        metadata=metadata,
        is_compliance=True,
        retention_days=2555,  # 7 years
    )


def log_kyc_verified(*, actor, user, submission_id: str, provider: str = "", request=None) -> None:
    """Record a successful KYC verification.

    Args:
        actor: Staff or system performing the verification.
        user: The user whose KYC was verified.
        submission_id: KYCSubmission PK.
        provider: Verification provider name.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.KYC_VERIFIED,
        event_category=EventCategory.KYC,
        action=f"KYC verified: user={getattr(user, 'email', str(user))} via {provider or 'system'}",
        actor=actor,
        resource_type="KYCSubmission",
        resource_id=submission_id,
        request=request,
        new_values={"verified_user": getattr(user, "email", str(user)), "provider": provider},
        is_compliance=True,
        retention_days=2555,
    )


def log_kyc_approved(
    *,
    actor,
    user,
    submission_id: str,
    provider_reference: str = "",
    request=None,
) -> None:
    """Record an approved KYC submission using the canonical approved event."""
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory, SeverityLevel

    AuditService.log(
        event_type=EventType.KYC_APPROVED,
        event_category=EventCategory.KYC,
        severity=SeverityLevel.INFO,
        action=f"KYC approved: user={getattr(user, 'email', str(user))}",
        actor=actor,
        actor_role="staff" if actor else "provider-webhook",
        resource_type="KYCSubmission",
        resource_id=submission_id,
        request=request,
        new_values={"provider_reference": provider_reference},
        is_compliance=True,
        retention_days=-1,
    )


def log_kyc_rejected(*, actor, user, submission_id: str, reason: str = "", request=None) -> None:
    """Record a KYC rejection.

    Args:
        actor: Staff or system rejecting KYC.
        user: The user whose KYC was rejected.
        submission_id: KYCSubmission PK.
        reason: Rejection reason.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.KYC_REJECTED,
        event_category=EventCategory.KYC,
        action=f"KYC rejected: user={getattr(user, 'email', str(user))} reason={reason[:200]}",
        actor=actor,
        resource_type="KYCSubmission",
        resource_id=submission_id,
        request=request,
        severity="warning",
        new_values={"reason": reason},
        is_compliance=True,
        retention_days=2555,
    )


def log_kyc_document_uploaded(
    *,
    actor,
    submission_id: str,
    document_id: str,
    document_type: str,
    created: bool,
    request=None,
) -> None:
    """Record a KYC document upload or replacement."""
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory, SeverityLevel

    AuditService.log(
        event_type=EventType.KYC_DOCUMENT_UPLOADED,
        event_category=EventCategory.KYC,
        severity=SeverityLevel.INFO,
        action=(
            f"KYC document {'created' if created else 'updated'}: "
            f"type={document_type} submission={submission_id}"
        ),
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="KycDocument",
        resource_id=document_id,
        request=request,
        new_values={
            "document_type": document_type,
            "submission_id": submission_id,
            "created": created,
        },
        is_compliance=True,
        retention_days=2555,
    )


def log_kyc_webhook(*, submission_id: str, provider: str, event: str, metadata: dict | None = None) -> None:
    """Record a KYC webhook event from an external provider.

    Args:
        submission_id: KYCSubmission PK if matched.
        provider: Provider name (dojah, youverify, etc.).
        event: Webhook event type string.
        metadata: Raw webhook payload summary.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.KYC_WEBHOOK,
        event_category=EventCategory.KYC,
        action=f"KYC webhook received: provider={provider} event={event} submission={submission_id}",
        resource_type="KYCSubmission",
        resource_id=submission_id,
        metadata=metadata,
        is_compliance=True,
        retention_days=2555,
    )


def log_bvn_verified(*, actor, resource_id: str, request=None) -> None:
    """Record a BVN verification event.

    Args:
        actor: The user being verified.
        resource_id: KYCSubmission or user PK.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.BVN_VERIFIED,
        event_category=EventCategory.KYC,
        action=f"BVN verified: user={getattr(actor, 'email', str(actor))}",
        actor=actor,
        resource_type="KYCSubmission",
        resource_id=resource_id,
        request=request,
        is_compliance=True,
        retention_days=2555,
    )
