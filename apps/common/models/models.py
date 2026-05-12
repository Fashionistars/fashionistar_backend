# apps/common/models/models.py
"""
COMPATIBILITY SHIM — Do not add new model definitions here.

This file was the original 1551-line monolith. It has been refactored
(Wave G1) into focused sub-modules:

    base.py              — TimeStampedModel
    soft_delete.py       — SoftDeleteModel, DeletedRecords,
                           DeletionAuditCounter, HardDeleteMixin
    analytics.py         — ModelAnalytics, UserLifecycleRegistry,
                           EntityLifecycleRegistry
    processed_webhook.py — CloudinaryProcessedWebhook

Existing migration files that execute:
    import apps.common.models.models

...will be satisfied by the re-exports below. All names point to the
single canonical class definition in the respective sub-module, so Django
will NEVER see duplicate model registrations.

DO NOT define any new Django model classes in this file.
"""
from __future__ import annotations

# ── Base ──────────────────────────────────────────────────────────────────────
from apps.common.models.base import TimeStampedModel

# ── Soft-delete infrastructure ────────────────────────────────────────────────
from apps.common.models.soft_delete import (
    SoftDeleteModel,
    DeletedRecords,
    DeletionAuditCounter,
    HardDeleteMixin,
)

# ── Analytics / lifecycle registries ─────────────────────────────────────────
from apps.common.models.analytics import (
    ModelAnalytics,
    UserLifecycleRegistry,
    EntityLifecycleRegistry,
)

# ── Webhook audit trail ───────────────────────────────────────────────────────
from apps.common.models.processed_webhook import CloudinaryProcessedWebhook

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
]
