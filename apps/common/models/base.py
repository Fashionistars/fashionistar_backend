# apps/common/models/base.py
"""
Core abstract base model for the Fashionistar platform.

Architecture:
    TimeStampedModel — provides UUID7 primary key plus auto-managed
    ``created_at`` / ``updated_at`` timestamps.  All domain models on
    the platform SHOULD inherit from this unless a custom PK scheme is
    explicitly required.

Design Principles:
    - UUID7 primary keys are globally unique AND time-ordered, enabling
      natural index locality without auto-increment collisions across
      distributed writers.
    - ``db_index=True`` on ``created_at`` supports efficient range
      queries and cursor-based pagination across all models.
"""

import uuid6
from django.db import models


# ================================================================
# 1. TIMESTAMPED MODEL
# ================================================================

class TimeStampedModel(models.Model):
    """Abstract base that provides UUID7 PK, created_at, and updated_at.

    All concrete models that inherit this gain:
        - A globally unique, time-ordered UUID7 primary key.
        - An indexed ``created_at`` field auto-set on INSERT.
        - An ``updated_at`` field auto-set on every UPDATE.

    Example:
        class Product(TimeStampedModel):
            name = models.CharField(max_length=255)
            # Inherits: id (UUID7), created_at, updated_at
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid6.uuid7,
        editable=False,
        help_text="UUID7 — globally unique, time-ordered primary key.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the record was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the record was last updated.",
    )
    active = models.BooleanField(default=True, db_index=True)
    class Meta:
        abstract = True


__all__ = ["TimeStampedModel"]
