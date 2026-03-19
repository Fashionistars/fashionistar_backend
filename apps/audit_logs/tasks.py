# apps/audit_logs/tasks.py
"""
Celery tasks for the audit_logs app.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


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

    Called directly via ``apply_async()`` from AuditService — independent
    Retries up to 2 times on transient DB errors; after that, logs and
    gives up (audit failure must never crash the main flow).
    """
    try:
        from apps.audit_logs.models import AuditEventLog
        actor_id = payload.pop("actor_id", None)
        obj = AuditEventLog(**payload)
        if actor_id:
            obj.actor_id = actor_id
        obj.save()
        logger.debug(
            "AuditEventLog written: event_type=%s actor=%s",
            payload.get("event_type"),
            payload.get("actor_email") or actor_id,
        )
    except Exception as exc:
        logger.warning(
            "write_audit_event failed (attempt %d/3): %s — payload event_type=%s",
            self.request.retries + 1,
            exc,
            payload.get("event_type"),
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
