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
app.conf.worker_hijack_root_logger = False

# ── TASK TIME LIMITS ──
# Global soft and hard execution limits to prevent hanging tasks from blocking workers.
app.conf.task_soft_time_limit = 300  # 5 minutes (soft limit, raises SoftTimeLimitExceeded)
app.conf.task_time_limit = 600       # 10 minutes (hard limit, kills worker process)

# Force-sanitize rediss:// broker and backend URLs to ensure ssl_cert_reqs is set.
# Celery's result backend throws ValueError if rediss:// URL is missing ssl_cert_reqs.
def _sanitize_celery_redis_url(url: str) -> str:
    if not url or not url.startswith("rediss://"):
        return url
    if "ssl_cert_reqs" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}ssl_cert_reqs=none"
    return url

if hasattr(app.conf, "broker_url") and app.conf.broker_url:
    app.conf.broker_url = _sanitize_celery_redis_url(app.conf.broker_url)
    if app.conf.broker_url.startswith("rediss://"):
        app.conf.broker_use_ssl = {"ssl_cert_reqs": "none"}

if hasattr(app.conf, "result_backend") and app.conf.result_backend:
    app.conf.result_backend = _sanitize_celery_redis_url(app.conf.result_backend)
    if app.conf.result_backend.startswith("rediss://"):
        app.conf.redis_backend_use_ssl = {"ssl_cert_reqs": "none"}
# Auto-discover tasks from all INSTALLED_APPS.
# Explicit list ensures future apps added to INSTALLED_APPS are auto-include.
app.autodiscover_tasks()
app.autodiscover_tasks(related_name="task")



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
    # ── Scheduler queues ──────────────────────────────────────────────────────
    Queue(
        "scheduler",
        Exchange("scheduler", type="direct"),
        routing_key="scheduler",
        queue_arguments={"x-max-priority": 5},
    ),
    Queue(
        "maintenance",
        Exchange("maintenance", type="direct"),
        routing_key="maintenance",
        queue_arguments={"x-max-priority": 3},
    ),
    Queue(
        "monitoring",
        Exchange("monitoring", type="direct"),
        routing_key="monitoring",
        queue_arguments={"x-max-priority": 3},
    ),
    Queue(
        "notifications",
        Exchange("notifications", type="direct"),
        routing_key="notifications",
        queue_arguments={"x-max-priority": 10},
    ),
    # ── DevOps queues ─────────────────────────────────────────────────────────
    Queue(
        "devops",
        Exchange("devops", type="direct"),
        routing_key="devops",
        queue_arguments={"x-max-priority": 3},
    ),
    # ── AI / ML queue — CPU-bound MediaPipe, CLIP, LangGraph ─────────────────
    # Workers: celery -A backend worker -Q ai --concurrency=1 --loglevel=info
    # (Low concurrency — ML models are CPU-intensive; 1-2 workers per machine)
    Queue(
        "ai",
        Exchange("ai", type="direct"),
        routing_key="ai",
        queue_arguments={"x-max-priority": 6},
    ),
    # ── AI Ingestion — high-frequency, lightweight signal-driven tasks ────────
    # Workers: celery -A backend worker -Q ai_ingestion --concurrency=4
    # (Higher concurrency than 'ai' — tasks are lightweight DB cache invalidations)
    Queue(
        "ai_ingestion",
        Exchange("ai_ingestion", type="direct"),
        routing_key="ai_ingestion",
        queue_arguments={"x-max-priority": 4},
    ),
    # ── Analytics queue — aggregation and reporting workloads ────────────────
    # Workers: celery -A backend worker -Q analytics --concurrency=2 --loglevel=info
    Queue(
        "analytics",
        Exchange("analytics", type="direct"),
        routing_key="analytics",
        queue_arguments={"x-max-priority": 5},
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

    # ── Scheduler App tasks ───────────────────────────────────────────────────
    "scheduler.execute_task": {"queue": "scheduler"},
    "scheduler.run_scheduled_task": {"queue": "scheduler"},
    "scheduler.cleanup_old_executions": {"queue": "maintenance"},
    "scheduler.check_missing_executions": {"queue": "monitoring"},
    "scheduler.monitor_task_performance": {"queue": "monitoring"},
    "scheduler.send_task_alerts": {"queue": "notifications"},

    # ── DevOps App tasks ──────────────────────────────────────────────────────
    "apps.devops.tasks.run_health_checks": {"queue": "devops"},
    "apps.devops.tasks.cleanup_old_health_checks": {"queue": "devops"},
    "apps.devops.tasks.generate_uptime_report": {"queue": "devops"},
    "apps.devops.tasks.check_deployment_status": {"queue": "devops"},
    "apps.devops.tasks.backup_deployment_logs": {"queue": "devops"},

    # ── Payment tasks (future — pre-wire so no code change needed) ────────────
    # "process_payment_webhook": {"queue": "payments"},
    # "send_payment_receipt":    {"queue": "emails"},

    # ── AI / ML tasks — routed to dedicated `ai` queue ────────────────────────
    # Worker: celery -A backend worker -Q ai --concurrency=1 --loglevel=info
    # Measurement pipeline
    "apps.ai.tasks.measurement_tasks.process_body_scan":    {"queue": "ai"},
    "apps.ai.tasks.measurement_tasks.prepare_scan_session": {"queue": "ai"},
    # Recommendation pipeline
    "apps.ai.tasks.recommendation_tasks.run_profile_recommendations":  {"queue": "ai"},
    "apps.ai.tasks.recommendation_tasks.generate_product_recommendations": {"queue": "ai"},
    "apps.ai.tasks.recommendation_tasks.run_product_embedding":         {"queue": "ai"},
    # Embedding generation (async, background — lower priority)
    "apps.ai.tasks.embedding_tasks.generate_product_embedding":         {"queue": "ai"},
    "apps.ai.tasks.embedding_tasks.batch_generate_embeddings":          {"queue": "ai"},
    "apps.ai.tasks.embedding_tasks.backfill_missing_embeddings":        {"queue": "ai"},
    # Analytics pipeline (migrated to apps/analytics)
    "apps.analytics.tasks.analytics_tasks.run_platform_analytics":             {"queue": "analytics"},
    "apps.analytics.tasks.analytics_tasks.run_user_behavior_analysis":         {"queue": "analytics"},
    "apps.analytics.tasks.analytics_tasks.run_product_performance_analysis":   {"queue": "analytics"},
    "apps.analytics.tasks.analytics_tasks.run_vendor_analytics":               {"queue": "analytics"},
    "apps.analytics.tasks.analytics_tasks.run_realtime_analytics":             {"queue": "analytics"},
    "apps.analytics.tasks.analytics_tasks.generate_daily_report":              {"queue": "analytics"},
    # Analytics aggregation rollups
    "apps.analytics.tasks.aggregation_tasks.rollup_1m":                        {"queue": "analytics"},
    "apps.analytics.tasks.aggregation_tasks.rollup_5m":                        {"queue": "analytics"},
    "apps.analytics.tasks.aggregation_tasks.rollup_1h":                        {"queue": "analytics"},
    "apps.analytics.tasks.aggregation_tasks.rollup_1d":                        {"queue": "analytics"},
    # DB ingestion — triggered by Django signals on model saves
    "apps.ai.tasks.ingestion_tasks.ingest_db_change":                   {"queue": "ai_ingestion"},
    "apps.ai.tasks.ingestion_tasks.refresh_trending_cache":             {"queue": "ai_ingestion"},
    "apps.ai.tasks.ingestion_tasks.cleanup_old_events":                 {"queue": "ai_ingestion"},
    "apps.ai.tasks.ingestion_tasks.rebuild_ai_context_cache":           {"queue": "ai_ingestion"},
    # Recommendation tasks
    "apps.ai.tasks.recommendation_tasks.run_profile_recommendations":   {"queue": "ai"},
    "apps.ai.tasks.recommendation_tasks.embed_product":                 {"queue": "ai"},
    "apps.ai.tasks.recommendation_tasks.embed_unembedded_products":     {"queue": "ai"},
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

    # ── Scheduler App Periodic Tasks ──────────────────────────────────────────
    "cleanup-old-executions": {
        "task": "scheduler.cleanup_old_executions",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "maintenance"},
    },
    "check-missing-executions": {
        "task": "scheduler.check_missing_executions",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "monitoring"},
    },
    "monitor-task-performance": {
        "task": "scheduler.monitor_task_performance",
        "schedule": crontab(minute=0),
        "options": {"queue": "monitoring"},
    },
    "send-task-alerts": {
        "task": "scheduler.send_task_alerts",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "notifications"},
    },

    # ── DevOps App Periodic Tasks ─────────────────────────────────────────────
    "run-devops-health-checks": {
        "task": "apps.devops.tasks.run_health_checks",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "devops"},
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

    # ── AI / ML Periodic Tasks (apps/ai — Phase 6) ────────────────────────────

    # Daily platform analytics — runs at 02:30 UTC (after audit cleanup at 02:00)
    # Generates 1-day, 7-day, and 30-day rolling reports
    "analytics-daily-report": {
        "task":     "apps.analytics.tasks.analytics_tasks.generate_daily_report",
        "schedule": crontab(hour=2, minute=30),
        "options":  {"queue": "analytics"},
    },

    # Analytics metric rollups (migrated to apps/analytics)
    "analytics-rollup-1m": {
        "task":     "apps.analytics.tasks.aggregation_tasks.rollup_1m",
        "schedule": crontab(minute="*"),
        "options":  {"queue": "analytics"},
    },
    "analytics-rollup-5m": {
        "task":     "apps.analytics.tasks.aggregation_tasks.rollup_5m",
        "schedule": crontab(minute="*/5"),
        "options":  {"queue": "analytics"},
    },
    "analytics-rollup-1h": {
        "task":     "apps.analytics.tasks.aggregation_tasks.rollup_1h",
        "schedule": crontab(minute=0),
        "options":  {"queue": "analytics"},
    },
    "analytics-rollup-1d": {
        "task":     "apps.analytics.tasks.aggregation_tasks.rollup_1d",
        "schedule": crontab(hour=0, minute=5),
        "options":  {"queue": "analytics"},
    },

    # Weekly embedding backfill — Sunday 03:00 UTC
    # Finds all active products without ProductEmbedding and generates them
    "ai-weekly-embedding-backfill": {
        "task":     "apps.ai.tasks.recommendation_tasks.embed_unembedded_products",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),   # Sunday
        "options":  {"queue": "ai"},
    },

    # Hourly trending products cache rebuild
    "ai-refresh-trending-cache": {
        "task":    "apps.ai.tasks.ingestion_tasks.refresh_trending_cache",
        "schedule": crontab(minute=0),   # Every hour on the hour
        "options": {"queue": "ai_ingestion"},
    },

    # Weekly DBChangeEvent cleanup — Monday 04:00 UTC (30-day retention)
    "ai-cleanup-old-events": {
        "task":    "apps.ai.tasks.ingestion_tasks.cleanup_old_events",
        "schedule": crontab(hour=4, minute=0, day_of_week=1),   # Monday
        "options": {"queue": "ai_ingestion"},
        "kwargs":  {"days": 30},
    },
}

app.conf.beat_scheduler = "django_celery_beat.schedulers:DatabaseScheduler"


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL HOOKS — Startup & Failure Observability
# ═══════════════════════════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)


@signals.setup_logging.connect
def config_loggers(*args, **kwargs):
    """
    Configure logging for Celery workers.

    We do nothing (pass) here because Django's dynamic AppConfig.ready() hook
    (BackendConfig in backend/apps.py) has already fully and dynamically configured
    all per-app loggers, root StreamHandler, safe rotating file handlers, process
    log suffixes, and propagation rules.

    Returning None/True here prevents Celery from overriding Django's ready() configuration.
    """
    pass


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