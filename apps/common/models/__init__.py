# apps/common/models/__init__.py
"""
Models package for apps.common.

This package was refactored (Wave G1) from a single 1551-line ``models.py``
monolith into three focused modules:

    base.py        — TimeStampedModel (UUID7 PK, timestamps)
    soft_delete.py — SoftDeleteModel, DeletedRecords, DeletionAuditCounter,
                     HardDeleteMixin
    analytics.py   — ModelAnalytics, UserLifecycleRegistry,
                     EntityLifecycleRegistry
    processed_webhook.py — CloudinaryProcessedWebhook

Backward Compatibility:
    All previously importable names remain available from ``apps.common.models``.
    No existing import site requires updating.

Examples:
    from apps.common.models import TimeStampedModel          # base
    from apps.common.models import SoftDeleteModel           # soft_delete
    from apps.common.models import ModelAnalytics            # analytics
    from apps.common.models import CloudinaryProcessedWebhook  # webhook
"""

from __future__ import annotations

# ── Base model ───────────────────────────────────────────────────────────────
from apps.common.models.base import TimeStampedModel

# ── Soft-delete infrastructure ───────────────────────────────────────────────
from apps.common.models.soft_delete import (
    SoftDeleteModel,
    DeletedRecords,
    DeletionAuditCounter,
    HardDeleteMixin,
)

# ── Analytics / lifecycle registries ────────────────────────────────────────
from apps.common.models.analytics import (
    ModelAnalytics,
    UserLifecycleRegistry,
    EntityLifecycleRegistry,
)

# ── Webhook audit trail ──────────────────────────────────────────────────────
from apps.common.models.processed_webhook import CloudinaryProcessedWebhook

# ── Performance telemetry audit log ──────────────────────────────────────────
from apps.common.models.telemetry import SlowPerformanceAuditLog

__all__ = [
    # base
    "TimeStampedModel",
    # soft_delete
    "SoftDeleteModel",
    "DeletedRecords",
    "DeletionAuditCounter",
    "HardDeleteMixin",
    # analytics
    "ModelAnalytics",
    "UserLifecycleRegistry",
    "EntityLifecycleRegistry",
    # webhook
    "CloudinaryProcessedWebhook",
    # telemetry
    "SlowPerformanceAuditLog",
]
