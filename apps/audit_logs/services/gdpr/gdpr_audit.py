# apps/audit_logs/services/gdpr/gdpr_audit.py
"""
GDPR audit hook — emits structured AuditEventLog rows for every GDPR
data-subject-rights action using the existing AuditEventLog model.

All actions use EventType.DATA_EXPORTED / ACCOUNT_SOFT_DELETED patterns
or the new COMPLIANCE event category for GDPR-specific events.
Never raises — always logs WARNING on failure.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Internal helper
# ─────────────────────────────────────────────────────────────────────────────


def _emit(
    *,
    user_id: str,
    action: str,
    performed_by_id: str | None,
    details: dict[str, Any],
) -> None:
    """
    Write one AuditEventLog row for a GDPR action.
    Deferred Celery dispatch to avoid blocking the caller.
    """
    try:
        from apps.audit_logs.tasks import log_audit_event_async
        log_audit_event_async.apply_async(
            kwargs={
                "event_type": "data_exported",          # best-fit existing EventType
                "event_category": "compliance",
                "severity": "warning",
                "action": f"GDPR: {action}",
                "actor_id": performed_by_id,
                "data_subject_id": user_id,
                "metadata": details,
                "is_compliance": True,
                "retention_days": 2555,                 # 7 years
                "legal_hold": action == "anonymize",    # freeze erasure rows
            },
            queue="audit",
        )
    except Exception:
        logger.warning(
            "GDPR audit emit failed: action=%s user=%s", action, user_id, exc_info=True
        )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


class _GDPRAudit:
    """Namespace class — all methods are static, no state."""

    @staticmethod
    def log_gdpr_action(
        *,
        user_id: str,
        action: str,
        performed_by_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Generic GDPR action log — used by GDPRService for all 5 Articles."""
        _emit(
            user_id=user_id,
            action=action,
            performed_by_id=performed_by_id,
            details=details or {},
        )

    @staticmethod
    def log_data_export(*, user_id: str, sections: list[str]) -> None:
        """Article 15 — Data Access / SAR export."""
        _emit(
            user_id=user_id,
            action="data_export",
            performed_by_id=user_id,
            details={"sections": sections, "article": "15"},
        )

    @staticmethod
    def log_anonymize(*, user_id: str, performed_by_id: str, counts: dict) -> None:
        """Article 17 — Right to Erasure / anonymization."""
        _emit(
            user_id=user_id,
            action="anonymize",
            performed_by_id=performed_by_id,
            details={"counts": counts, "article": "17", "irreversible": True},
        )

    @staticmethod
    def log_portability_export(*, user_id: str) -> None:
        """Article 20 — Data Portability."""
        _emit(
            user_id=user_id,
            action="portability_export",
            performed_by_id=user_id,
            details={"format": "json", "article": "20"},
        )

    @staticmethod
    def log_objection(*, user_id: str, processing_purpose: str) -> None:
        """Article 21 — Right to Object."""
        _emit(
            user_id=user_id,
            action="object_to_processing",
            performed_by_id=user_id,
            details={"processing_purpose": processing_purpose, "article": "21"},
        )


gdpr_audit = _GDPRAudit()
