# backend/celery.py
"""
FASHIONISTAR — Enterprise Celery Application Configuration
==========================================================
This file is the SINGLE SOURCE OF TRUTH for all Celery runtime configuration:

  ✅ App instantiation + Django settings namespace bridge
  ✅ 8 priority-stratified queues (webhooks → default)
  ✅ Explicit task → queue routing table
  ✅ Celery Beat periodic task schedule
  ✅ Startup signal hooks for supervisor logging
  ✅ Task failure signal hooks for alerting

Architecture Pattern
────────────────────
Mirrors Paycore fintech reference (paycore-api-1/paycore/celery.py) and
the HNG Stage-3 production pattern (hng-stage-3-agent-main/core/celery.py).

All queue/routing config lives HERE — NOT in settings files.
settings/base.py only provides the broker URL and basic serialiser settings
(CELERY_BROKER_URL, CELERY_RESULT_BACKEND, CELERY_TASK_SERIALIZER, etc.).

Workers
───────
Start workers from the project root:

  # All queues (development)
  make celery

  # Production — dedicated workers per queue tier
  celery -A backend worker -Q webhooks  --concurrency=4  --loglevel=INFO
  celery -A backend worker -Q audit     --concurrency=2  --loglevel=INFO
  celery -A backend worker -Q emails    --concurrency=4  --loglevel=INFO
  celery -A backend worker -Q transforms --concurrency=2 --loglevel=INFO
  celery -A backend worker -Q cleanup,bulk,default --concurrency=2

  # Beat scheduler
  celery -A backend beat --loglevel=INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler

Reference
─────────
  Cloudinary tasks : apps/common/tasks/cloudinary.py
  Audit tasks      : apps/audit_logs/tasks.py
  Notification tasks: apps/common/tasks/notifications.py
"""

from __future__ import annotations

import logging
import os

from celery import Celery, signals
from celery.schedules import crontab
from kombu import Exchange, Queue

# ─────────────────────────────────────────────────────────────────────────────
# DJANGO SETTINGS BOOTSTRAP
# ─────────────────────────────────────────────────────────────────────────────
# Must be set BEFORE the Celery app is instantiated so that
# app.config_from_object() can pull CELERY_* vars from Django settings.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

# ─────────────────────────────────────────────────────────────────────────────
# APPLICATION INSTANCE
# ─────────────────────────────────────────────────────────────────────────────
app = Celery("backend")

# Using a string here means the worker doesn't have to serialize the
# configuration object to child processes.
# namespace="CELERY" means all celery-related settings in Django's settings
# file should have the `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all INSTALLED_APPS.
# Explicit list ensures future apps added to INSTALLED_APPS are auto-include.
app.autodiscover_tasks()


# ═══════════════════════════════════════════════════════════════════════════════
# QUEUE DEFINITIONS  — 8 Priority-Stratified Queues
# ═══════════════════════════════════════════════════════════════════════════════
#
# Priority levels (x-max-priority=10 — RabbitMQ / Redis via amqp):
#   10 — webhooks  : Cloudinary webhook processing (sub-second required)
#   10 — emails    : Transactional emails (OTP, password reset)
#   10 — payments  : Payment events (PCI compliance)
#    7 — audit     : Audit log writes (compliance trail, GDPR, non-blocking)
#    5 — transforms: Eager image/video transforms (2K/4K/8K generation)
#    3 — cleanup   : CDN cache invalidation, Cloudinary asset deletion
#    2 — bulk      : Bulk URL sync, vendor gallery batch operations
#    1 — default   : Catch-all for everything else
#
# PRODUCTION SIZING GUIDE (Render.com / AWS ECS):
#   webhooks/emails/payments → 4 concurrency workers (I/O bound)
#   transforms               → 2 concurrency workers (CPU bound — PIL/FFmpeg)
#   audit                    → 2 concurrency workers (DB bound)
#   bulk/cleanup/default     → 2 concurrency workers (background)

app.conf.task_queues = (
    # ── Highest priority — user-facing or compliance-critical ────────────────
    Queue(
        "webhooks",
        Exchange("webhooks", type="direct"),
        routing_key="webhooks",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "emails",
        Exchange("emails", type="direct"),
        routing_key="emails",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "payments",
        Exchange("payments", type="direct"),
        routing_key="payments",
        queue_arguments={"x-max-priority": 10},
    ),
    # ── Medium-high priority — compliance audit trail ─────────────────────────
    Queue(
        "audit",
        Exchange("audit", type="direct"),
        routing_key="audit",
        queue_arguments={"x-max-priority": 7},
    ),
    # ── Medium priority — server-side image/video processing ──────────────────
    Queue(
        "transforms",
        Exchange("transforms", type="direct"),
        routing_key="transforms",
        queue_arguments={"x-max-priority": 5},
    ),
    # ── Low priority — cleanup / housekeeping ─────────────────────────────────
    Queue(
        "cleanup",
        Exchange("cleanup", type="direct"),
        routing_key="cleanup",
        queue_arguments={"x-max-priority": 3},
    ),
    # ── Batch / bulk operations ──────────────────────────────────────────────
    Queue(
        "bulk",
        Exchange("bulk", type="direct"),
        routing_key="bulk",
        queue_arguments={"x-max-priority": 2},
    ),
    # ── Default catch-all ─────────────────────────────────────────────────────
    Queue(
        "default",
        Exchange("default", type="direct"),
        routing_key="default",
        queue_arguments={"x-max-priority": 1},
    ),
)

app.conf.task_default_queue = "default"
app.conf.task_default_exchange = "default"
app.conf.task_default_routing_key = "default"


# ═══════════════════════════════════════════════════════════════════════════════
# TASK ROUTING TABLE
# ═══════════════════════════════════════════════════════════════════════════════
# Maps Celery task names → queue names.
# Any unmapped task falls into the 'default' queue.
#
# CONVENTION: Use short task names (set via the `name=` param on @shared_task)
# rather than fully-qualified Python module paths — shorter names are
# serialisation-safe and easier to monitor in Flower / Redis-Commander.

app.conf.task_routes = {
    # ── Cloudinary Webhooks — highest priority (sub-second latency needed) ────
    "process_cloudinary_upload_webhook": {"queue": "webhooks"},

    # ── Audit Logging — compliance-critical; dedicated worker pool ────────────
    "write_audit_event":   {"queue": "audit"},
    "audit_log_cleanup":   {"queue": "audit"},

    # ── Image / Video Transforms — CPU/IO heavy; separate workers ─────────────
    "generate_eager_transformations": {"queue": "transforms"},

    # ── Cleanup / CDN Invalidation — low priority; no SLA ────────────────────
    "delete_cloudinary_asset_task": {"queue": "cleanup"},
    "purge_cloudinary_cache":       {"queue": "cleanup"},

    # ── Bulk / Batch operations — background; no SLA ──────────────────────────
    "bulk_sync_cloudinary_urls": {"queue": "bulk"},

    # ── Notification tasks — transactional; high priority ────────────────────
    "apps.common.tasks.send_account_status_email": {"queue": "emails"},
    "apps.common.tasks.send_account_status_sms":   {"queue": "emails"},

    # ── Payment tasks (future — pre-wire so no code change needed) ────────────
    # "process_payment_webhook": {"queue": "payments"},
    # "send_payment_receipt":    {"queue": "emails"},
}


# ═══════════════════════════════════════════════════════════════════════════════
# CELERY BEAT — Periodic Task Schedule
# ═══════════════════════════════════════════════════════════════════════════════
# For production, use django_celery_beat DatabaseScheduler so schedules can be
# managed via Django admin without restarting workers.
#
# These defaults are loaded if no DB-stored schedule exists yet.

app.conf.beat_schedule = {
    # ── Keep Render.com free-tier service alive (ping every 100 seconds) ────────────
    "keep-render-service-awake": {
        "task":     "keep_service_awake",
        "schedule": 100.0,   # Every 100 seconds
        "options":  {"queue": "default"},
    },

    # ── Audit log data-retention cleanup (daily at 2 AM UTC) ─────────────────
    # Purges expired non-compliance AuditEventLog rows (90-day default) and
    # old CloudinaryProcessedWebhook records (90-day default).
    # compliance-flagged records (is_compliance=True) are NEVER deleted.
    "audit-log-cleanup": {
        "task":     "audit_log_cleanup",
        "schedule": crontab(hour=2, minute=0),
        "options":  {"queue": "audit"},
    },

    # ── Future periodic tasks (pre-register; activate by uncommenting) ────────
    # "nightly-bulk-cloudinary-sync": {
    #     "task":     "bulk_sync_cloudinary_urls",
    #     "schedule": crontab(hour=3, minute=0),
    #     "options":  {"queue": "bulk"},
    # },
    # "hourly-cdn-cache-purge": {
    #     "task":     "purge_cloudinary_cache",
    #     "schedule": crontab(minute=0),
    #     "options":  {"queue": "cleanup"},
    # },
}

app.conf.beat_scheduler = "django_celery_beat.schedulers:DatabaseScheduler"


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL HOOKS — Startup & Failure Observability
# ═══════════════════════════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)


@signals.after_task_publish.connect
def on_task_published(sender=None, headers=None, body=None, **kwargs):
    """Log task dispatch for observability (DEBUG level to avoid log spam)."""
    task_name = (headers or {}).get("task", sender or "unknown")
    logger.debug("[Celery] Task dispatched: %s", task_name)


@signals.task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    """
    Central failure hook — fires on every unhandled task exception.

    In production, send to Sentry / Datadog / PagerDuty by replacing
    the logger.error call with your alerting library call.
    """
    task_name = getattr(sender, "name", str(sender))
    logger.error(
        "[Celery] TASK FAILED: task=%s task_id=%s error=%s",
        task_name,
        task_id,
        exception,
    )


@signals.worker_ready.connect
def on_worker_ready(sender=None, **kwargs):
    """Log clean worker startup for ops / log-aggregators."""
    logger.info(
        "[Celery] Worker ready: hostname=%s",
        getattr(sender, "hostname", "unknown"),
    )


@signals.celeryd_after_setup.connect
def on_worker_setup(sender=None, instance=None, **kwargs):
    """
    Fires once after a worker process initialises.
    Use to pre-warm caches or validate config at boot time.
    """
    logger.info(
        "[Celery] Worker setup complete. Queues: %s",
        list(app.conf.task_queues),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DEBUG TASK — Useful for smoke-testing broker connectivity
# ═══════════════════════════════════════════════════════════════════════════════

@app.task(bind=True, name="debug_task", ignore_result=True)
def debug_task(self):
    """
    Smoke-test task. Call via:
        python manage.py shell -c "from backend.celery import debug_task; debug_task.delay()"
    """
    logger.info("[Celery] debug_task received: request=%r", self.request)
    print(f"[Celery] debug_task: {self.request!r}")