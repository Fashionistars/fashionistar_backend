# apps/ai/models/db_change_event.py
"""
DBChangeEvent — Log of database changes ingested by the AI engine.

Every time a watched model is saved, a DBChangeEvent row is created.
The AI engine processes these events to keep its knowledge current.

Architecture:
  - Write-once (no updates, no deletes — change events are immutable)
  - Celery ingestion_tasks.py processes pending events in batches
  - Processed events are marked is_processed=True (never deleted — audit trail)
  - Retention: 30 days (controlled by periodic cleanup task)
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class DBChangeEvent(TimeStampedModel):
    """
    Immutable record of a database model save event.

    When any watched model (Product, User, MeasurementProfile, etc.) is saved,
    a DBChangeEvent is created by the post_save signal in apps/ai/signals/.
    The AI ingestion pipeline processes these in FIFO order.

    Attributes:
        event_id: Immutable UUID for event identification
        app_label: Django app name (e.g., 'product', 'measurements')
        model_name: Django model name (e.g., 'Product', 'MeasurementProfile')
        object_id: PK of the changed instance (as string for flexibility)
        event_type: 'created' or 'updated'
        is_processed: True after AI engine has ingested this change
        processed_at: When the AI engine processed this event
        celery_task_id: Celery task that processed this event
    """

    class EventType(models.TextChoices):
        CREATED = "created", _("Created")
        UPDATED = "updated", _("Updated")
        DELETED = "deleted", _("Deleted")

    event_id = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        verbose_name=_("Event ID"),
    )
    app_label  = models.CharField(max_length=50,  db_index=True, verbose_name=_("App Label"))
    model_name = models.CharField(max_length=100, db_index=True, verbose_name=_("Model Name"))
    object_id  = models.CharField(
        max_length=200,
        verbose_name=_("Object ID"),
        help_text=_("Primary key of the changed object, stored as string."),
    )
    event_type = models.CharField(
        max_length=10,
        choices=EventType.choices,
        default=EventType.UPDATED,
        verbose_name=_("Event Type"),
    )
    is_processed   = models.BooleanField(default=False, db_index=True, verbose_name=_("Processed"))
    processed_at   = models.DateTimeField(null=True, blank=True, verbose_name=_("Processed At"))
    celery_task_id = models.CharField(max_length=200, blank=True, verbose_name=_("Celery Task ID"))

    class Meta:
        verbose_name = _("DB Change Event")
        verbose_name_plural = _("DB Change Events")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_processed", "created_at"], name="ai_dbc_pending_idx"),
            models.Index(fields=["app_label", "model_name"],    name="ai_dbc_model_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.event_type}] {self.app_label}.{self.model_name}#{self.object_id}"
