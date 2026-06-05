# apps/order/models/order_timeline.py
"""
OrderTimeline — immutable ordered status history with actor attribution.

Architecture Rules:
  - TimeStampedModel only (append-only, no soft-delete, no updates).
  - Each record represents a single status transition, capturing who
    triggered it, when, from what previous state, and any commentary.
  - Populated exclusively by OrderService — never written from admin directly.
  - actor_role stored as snapshot (role may change after the fact).
  - `is_system_event` = True for automated Celery / webhook transitions.

Write safety:
  - All callers must be inside transaction.atomic() (enforced in OrderService).
  - select_for_update() on the parent Order row is the caller's responsibility.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class OrderTimeline(TimeStampedModel):
    """
    Single, immutable status transition entry in the order timeline.

    Provides a tamper-evident audit trail for every state change
    an Order passes through, from 'pending' to 'delivered' or 'refunded'.

    Attributes:
        order: Parent Order being transitioned.
        from_status: Previous status slug (snapshot at transition time).
        to_status: New status slug after this transition.
        actor: User who triggered the transition. Null = system/Celery.
        actor_role: Snapshot of actor's primary role at transition time.
        actor_ip: IP address of the triggering request (if HTTP-triggered).
        note: Optional staff/system commentary visible in the admin timeline.
        is_system_event: True if triggered by background task / webhook.
        metadata: Arbitrary JSON for carrier updates, webhook payloads, etc.
    """

    order = models.ForeignKey(
        "order.Order",
        on_delete=models.CASCADE,
        related_name="timeline_events",
        verbose_name=_("Order"),
    )
    from_status = models.CharField(
        max_length=30,
        blank=True,
        verbose_name=_("Previous Status"),
        help_text=_("Status snapshot BEFORE this transition."),
    )
    to_status = models.CharField(
        max_length=30,
        verbose_name=_("New Status"),
        help_text=_("Status snapshot AFTER this transition."),
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_timeline_events",
        verbose_name=_("Actor"),
        help_text=_("User who triggered transition. Null = system/Celery."),
    )
    actor_role = models.CharField(
        max_length=30,
        blank=True,
        verbose_name=_("Actor Role"),
        help_text=_("Snapshot of actor's primary role at transition time."),
    )
    actor_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("Actor IP"),
    )
    note = models.TextField(
        blank=True,
        verbose_name=_("Note"),
        help_text=_("Staff/system commentary visible in the admin timeline."),
    )
    is_system_event = models.BooleanField(
        default=False,
        verbose_name=_("System Event"),
        help_text=_("True if triggered by Celery task, webhook, or cron."),
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Metadata"),
        help_text=_("Carrier updates, webhook payloads, or other context."),
    )

    class Meta:
        verbose_name = _("Order Timeline Event")
        verbose_name_plural = _("Order Timeline Events")
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["order", "created_at"], name="otl_order_created_idx"),
            models.Index(fields=["to_status", "created_at"], name="otl_status_created_idx"),
        ]

    def __str__(self) -> str:
        actor_label = str(self.actor) if self.actor_id else "system"
        return (
            f"Order#{self.order_id}: {self.from_status or '?'} → "
            f"{self.to_status} by {actor_label}"
        )
