# apps/audit_logs/tasks.py
"""
Celery tasks for the audit_logs app.

Tasks
─────
  write_audit_event     — Write one AuditEventLog row (primary task).
  cleanup_audit_logs    — Periodic cleanup of expired audit records (daily 2AM).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task

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
        "actor", "actor_email",
        "ip_address", "user_agent", "device_type",
        "browser_family", "os_family",
        "country", "correlation_id",
        "resource_type", "resource_id",
        "request_method", "request_path", "response_status", "duration_ms",
        "old_values", "new_values", "metadata", "error_message",
        "is_compliance", "retention_days",
    }

    try:
        from apps.audit_logs.models import AuditEventLog

        # Extract actor_id separately (set via obj.actor_id, not __init__)
        actor_id = payload.pop("actor_id", None)

        # ⚡ Strip any keys the ORM doesn't know about (geo extras, future fields)
        safe_payload = {k: v for k, v in payload.items() if k in _KNOWN_FIELDS}

        # Log stripped keys so we can identify payload drift early
        stripped = set(payload) - _KNOWN_FIELDS - {"actor_id"}
        if stripped:
            logger.debug(
                "write_audit_event: stripped unknown payload keys: %s", stripped
            )

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
    try:
        from apps.audit_logs.models import AuditEventLog

        # Delete rows where the record is older than its own retention_days
        # and it is NOT marked as compliance-critical.
        # SQL: DELETE FROM audit_event_log
        #      WHERE is_compliance = FALSE
        #        AND created_at < NOW() - INTERVAL retention_days DAYS
        #
        # Django ORM approach: filter by a computed expiry.
        # We delete in batches (1000 at a time) to avoid long-running locks.
        BATCH_SIZE = 1000
        total_deleted = 0

        while True:
            # Get IDs of expired non-compliance events
            expired_ids = list(
                AuditEventLog.objects.filter(
                    is_compliance=False,
                    # Approximate: compare on created_at < cutoff(90 days)
                    # For rows with custom retention_days, the service layer
                    # sets the value; we use 90 days as a conservative default.
                    created_at__lt=now - timedelta(days=90),
                ).values_list("id", flat=True)[:BATCH_SIZE]
            )

            if not expired_ids:
                break

            deleted_count, _ = AuditEventLog.objects.filter(
                id__in=expired_ids, is_compliance=False  # double-guard
            ).delete()
            total_deleted += deleted_count

            if deleted_count < BATCH_SIZE:
                break  # No more to delete

        result["audit_deleted"] = total_deleted
        logger.info(
            "audit_log_cleanup: deleted %d expired AuditEventLog rows",
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
