# apps/common/models/__init__.py
"""
Models package for apps.common.

This file turns the models/ directory into a Python package and re-exports
every model class that was previously importable from the flat
``apps.common.models`` module.

Backward-compatible: any code that previously did
    from apps.common.models import TimeStampedModel
still works without change.

Exports
─────────────────────────────────────────────────────────────────
 From models.py (infrastructure / abstract base models):
   TimeStampedModel          — UUID7 PK, created_at, updated_at
   SoftDeleteModel           — soft-delete with archive & restore
   DeletedRecords            — archive table for soft-deleted rows
   DeletionAuditCounter      — per-model deletion counters
   ModelAnalytics            — globalrow count analytics
   HardDeleteMixin           — protected permanent deletion

 From processed_webhook.py (Phase 4 — Cloudinary idempotency):
   CloudinaryProcessedWebhook — immutable audit trail for webhooks
"""
from __future__ import annotations

# ── Infrastructure / abstract base models (from models.py) ──────────────────
from .models import (
    TimeStampedModel,
    SoftDeleteModel,
    DeletedRecords,
    DeletionAuditCounter,
    ModelAnalytics,
)

# Pull in everything else from models.py for true backward compatibility
# (covers HardDeleteMixin, SoftDeleteManager, etc.)
from .models import *  # noqa: F401, F403

# ── Phase 4: Webhook audit trail ────────────────────────────────────────────
from .processed_webhook import CloudinaryProcessedWebhook


__all__ = [
    # Infrastructure
    "TimeStampedModel",
    "SoftDeleteModel",
    "DeletedRecords",
    "DeletionAuditCounter",
    "ModelAnalytics",
    # Phase 4
    "CloudinaryProcessedWebhook",
]
