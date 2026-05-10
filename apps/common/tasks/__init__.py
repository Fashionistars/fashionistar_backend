# apps/common/tasks/__init__.py
"""
``apps.common.tasks`` package.

Celery Autodiscovery
────────────────────
Celery's autodiscovery mechanism calls
    ``celery.autodiscover_tasks(["apps.common", ...])``
which resolves to importing ``apps.common.tasks``.
Since this IS the package ``__init__.py``, Celery finds it immediately.

All task functions are imported here so that:
    1. Celery registers them at worker startup.
    2. External callers can do ``from apps.common.tasks import <task>``
       exactly as before (backward-compatible).

Sub-modules:
    health.py        — Periodic service-alive ping.
    notifications.py — Account-status email & SMS.
    analytics.py     — ModelAnalytics counter update.
    cloudinary.py    — Cloudinary upload/delete/webhook/bulk tasks.
    lifecycle.py     — UserLifecycleRegistry CRUD + login counter.
"""

# ── Health ────────────────────────────────────────────────────────────────────
from apps.common.tasks.health import (            # noqa: F401
    keep_service_awake,
)

# ── Notifications ─────────────────────────────────────────────────────────────
from apps.common.tasks.notifications import (     # noqa: F401
    send_account_status_email,
    send_account_status_sms,
)

# ── Analytics ─────────────────────────────────────────────────────────────────
from apps.common.tasks.analytics import (         # noqa: F401
    update_model_analytics_counter,
)

# ── Cloudinary ────────────────────────────────────────────────────────────────
from apps.common.tasks.cloudinary import (        # noqa: F401
    delete_cloudinary_asset_task,
    process_cloudinary_upload_webhook,
    generate_eager_transformations,
    purge_cloudinary_cache,
    bulk_sync_cloudinary_urls,
)

# ── User Lifecycle ────────────────────────────────────────────────────────────
from apps.common.tasks.lifecycle import (         # noqa: F401
    upsert_user_lifecycle_registry,
    increment_lifecycle_login_counter,
)

__all__ = [
    # health
    "keep_service_awake",
    # notifications
    "send_account_status_email",
    "send_account_status_sms",
    # analytics
    "update_model_analytics_counter",
    # cloudinary
    "delete_cloudinary_asset_task",
    "process_cloudinary_upload_webhook",
    "generate_eager_transformations",
    "purge_cloudinary_cache",
    "bulk_sync_cloudinary_urls",
    # lifecycle
    "upsert_user_lifecycle_registry",
    "increment_lifecycle_login_counter",
]
