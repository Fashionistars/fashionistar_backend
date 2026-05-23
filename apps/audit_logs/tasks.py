# apps/audit_logs/tasks.py
"""
Celery tasks for the audit_logs app.

Tasks
─────
  write_audit_event     — Write one AuditEventLog row (primary task).
  cleanup_audit_logs    — Periodic cleanup of expired audit records (daily 2AM).
                          Respects per-row retention_days (NDPR/PCI-DSS).

Compliance notes:
  - Rows with is_compliance=True are NEVER deleted, regardless of retention_days.
  - Rows with retention_days=-1 (permanent) are excluded by is_compliance=False guard.
  - Batch deletes (1000/cycle) prevent long table locks in production PostgreSQL.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import DurationField, ExpressionWrapper, F
from django.utils import timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 1. WRITE AUDIT EVENT
# ═══════════════════════════════════════════════════════════════════════════

@shared_task(
    name="write_audit_event",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    ignore_result=True,
)
def write_audit_event(self, payload: dict) -> None:
    """
    Write an AuditEventLog row from the given payload dict.

    Called via apply_async() from AuditService — fully async, never blocks
    the main Django request thread.

    Retries up to 2 times on transient DB errors. After that, logs the
    failure as WARNING and gives up — audit failures MUST never crash the
    main request flow.
    """
    # ── Known AuditEventLog field names (allowlist) ───────────────────────────
    # Geo-enrichment services may add extra keys (country_code, city, region,
    # asn, …) that are NOT columns on AuditEventLog. Strip them here so we
    # never crash with "unexpected keyword argument".
    _KNOWN_FIELDS = {
        "event_type", "event_category", "severity", "action",
        "actor", "actor_email", "actor_role", "session_id",
        "ip_address", "user_agent", "device_type",
        "browser_family", "os_family",
        "country", "country_code", "city", "correlation_id",
        "resource_type", "resource_id",
        "request_method", "request_path", "response_status", "duration_ms",
        "old_values", "new_values", "metadata", "error_message",
        "is_compliance", "retention_days",
        # ── Wave B3: Frontend client context fields (migration 0005) ──────────
        # Added for device-level audit trails per GDPR/NDPR/PCI-DSS requirements.
        # These are populated from X-Client-* request headers via AuditMiddleware.
        "client_device_id", "client_timezone", "client_locale", "client_platform",
        "client_geo_lat", "client_geo_lng", "client_geo_accuracy_m",
    }


    try:
        from apps.audit_logs.models import AuditEventLog

        # Extract actor_id separately (set via obj.actor_id, not __init__)
        actor_id = payload.get("actor_id")

        # ⚡ Strip any keys the ORM doesn't know about (geo extras, future fields)
        safe_payload = {k: v for k, v in payload.items() if k in _KNOWN_FIELDS}

        # Log stripped keys so we can identify payload drift early
        stripped = set(payload) - _KNOWN_FIELDS - {"actor_id"}
        if stripped:
            logger.debug(
                "write_audit_event: stripped unknown payload keys: %s", stripped
            )

        # AuditEventLog rows are append-only by design, so every audit event
        # must be persisted as a fresh row even when a correlation_id repeats.
        obj = AuditEventLog(**safe_payload)

        if actor_id:
            obj.actor_id = actor_id
        obj.save()

        logger.debug(
            "AuditEventLog written: event_type=%s actor=%s",
            safe_payload.get("event_type"),
            safe_payload.get("actor_email") or actor_id,
        )
    except Exception as exc:
        logger.warning(
            "write_audit_event failed (attempt %d/3): %s — event_type=%s",
            self.request.retries + 1,
            exc,
            payload.get("event_type"),
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)


# ═══════════════════════════════════════════════════════════════════════════
# 2. AUDIT LOG CLEANUP — Production data retention enforcement
# ═══════════════════════════════════════════════════════════════════════════

@shared_task(
    name="audit_log_cleanup",
    bind=True,
    max_retries=1,
    default_retry_delay=300,   # 5 min retry on failure
    ignore_result=True,
)
def cleanup_audit_logs(self) -> dict:
    """
    Daily cleanup of expired audit log records.

    Retention policy (from AuditEventLog.retention_days field):
    ─────────────────────────────────────────────────────────────
      compliance events (is_compliance=True): 7 years (2555 days)
      security events:                        2 years (730 days)
      system/debug events:                    90 days  (default)
      webhook records (ProcessedWebhook):     90 days

    This task deletes rows where:
      created_at < (now() - retention_days)  AND  is_compliance = False

    NEVER deletes compliance-marked events (PCI, GDPR, financial).
    Scheduled: daily at 2 AM UTC via CELERY_BEAT_SCHEDULE in base.py.

    Returns:
        dict with counts of deleted records per category.
    """
    now = timezone.now()
    result = {
        "audit_deleted": 0,
        "webhook_deleted": 0,
        "run_at": now.isoformat(),
    }

    # ── Step 1: Delete expired non-compliance AuditEventLog rows ─────────
    #
    # Production-grade strategy (NDPR / PCI-DSS Art. 17):
    #   We annotate each row with its individual expiry date using a DB-side
    #   ExpressionWrapper so each row's own retention_days column drives deletion.
    #   This means a 7-year financial event and a 90-day debug event co-exist
    #   in the same table with ZERO risk of premature erasure.
    #
    # Excluded from deletion:
    #   - is_compliance = True  (hard financial / GDPR compliance records)
    #   - retention_days <= 0   (permanent retention sentinel — set to -1 by convention)
    try:
        from apps.audit_logs.models import AuditEventLog

        BATCH_SIZE = 1000
        total_deleted = 0

        while True:
            # Annotate rows with a computed expiry timestamp:
            #   expiry_at = created_at + retention_days (converted to interval)
            # Then filter: expiry_at < now AND is_compliance=False AND retention_days > 0
            expired_ids = list(
                AuditEventLog.objects.filter(
                    is_compliance=False,
                    retention_days__gt=0,   # exclude permanent (-1) rows
                )
                .annotate(
                    expiry_at=ExpressionWrapper(
                        F("created_at")
                        + ExpressionWrapper(
                            F("retention_days") * timedelta(days=1),
                            output_field=DurationField(),
                        ),
                        output_field=DurationField(),
                    )
                )
                .filter(expiry_at__lt=now)
                .values_list("id", flat=True)[:BATCH_SIZE]
            )

            if not expired_ids:
                break

            deleted_count, _ = AuditEventLog.objects.filter(
                id__in=expired_ids,
                is_compliance=False,  # double-guard — never delete compliance rows
            ).delete()
            total_deleted += deleted_count

            if deleted_count < BATCH_SIZE:
                break  # exhausted eligible rows

        result["audit_deleted"] = total_deleted
        logger.info(
            "audit_log_cleanup: deleted %d expired AuditEventLog rows (per-row retention)",
            total_deleted,
        )

    except Exception as exc:
        logger.error("audit_log_cleanup: AuditEventLog cleanup failed: %s", exc)

    # ── Step 2: Delete old CloudinaryProcessedWebhook rows (90-day default) ─
    try:
        from apps.common.models import CloudinaryProcessedWebhook

        cutoff = now - timedelta(days=90)
        wh_deleted, _ = CloudinaryProcessedWebhook.objects.filter(
            processed_at__lt=cutoff
        ).delete()
        result["webhook_deleted"] = wh_deleted

        logger.info(
            "audit_log_cleanup: deleted %d old CloudinaryProcessedWebhook rows",
            wh_deleted,
        )

    except Exception as exc:
        logger.error(
            "audit_log_cleanup: CloudinaryProcessedWebhook cleanup failed: %s", exc
        )

    logger.info(
        "audit_log_cleanup complete: audit=%d webhook=%d",
        result["audit_deleted"],
        result["webhook_deleted"],
    )
    return result
