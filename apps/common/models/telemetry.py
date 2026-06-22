# apps/common/models/telemetry.py
"""
FASHIONISTAR — Core Web Vitals SLA Audit Log Model.

This model persists SLA-breaching performance metrics (LCP, INP, CLS, FID)
sent from the Next.js storefront edge layer to the Django backend.

Only metrics that exceed the defined SLA thresholds are stored here:
  - LCP > 2500ms
  - FID > 100ms
  - CLS > 0.1
  - INP > 200ms

Healthy metrics are tracked in Redis counters (zero-DB-write path).
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class SlowPerformanceAuditLog(models.Model):
    """
    Append-only audit table for storefront Core Web Vital SLA breaches.

    This table is written to ONLY when a metric exceeds the defined SLA
    threshold. It provides the data source for the admin performance warning
    board and automated alerting systems (Sentry / Datadog).

    Design Decisions:
      - No foreign keys: metrics are captured before any user session exists.
      - ip_address is stored hashed (or anonymized) in production.
      - `logged_at` is set in application code (not auto_now_add) so it
        precisely matches the browser-side metric timestamp.
    """

    # ── Metric Identity ───────────────────────────────────────────────────────
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_("Log ID"),
    )
    metric_id = models.CharField(
        max_length=128,
        db_index=True,
        verbose_name=_("Metric ID"),
        help_text=_(
            "Unique browser-generated metric ID (from web-vitals library). "
            "Used to deduplicate multiple readings for the same navigation."
        ),
    )

    # ── Metric Data ───────────────────────────────────────────────────────────
    metric_name = models.CharField(
        max_length=10,
        db_index=True,
        verbose_name=_("Metric Name"),
        help_text=_("Core Web Vital name: LCP, FID, CLS, INP, TTFB, FCP."),
    )
    metric_value = models.FloatField(
        verbose_name=_("Metric Value"),
        help_text=_("Measured value. Units: ms for time-based metrics; unitless for CLS."),
    )

    # ── Request Context ───────────────────────────────────────────────────────
    page_path = models.CharField(
        max_length=512,
        verbose_name=_("Page Path"),
        help_text=_("URL path where the metric was measured, e.g., '/' or '/products/agbada-senator'."),
    )
    user_agent = models.TextField(
        blank=True,
        default="",
        verbose_name=_("User Agent"),
        help_text=_("Browser UA string. Used to correlate slow metrics with specific browser families."),
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("Client IP Address"),
        help_text=_("Anonymized or hashed in production. Retained for 30 days per GDPR Article 5."),
    )

    # ── Audit Timestamps ──────────────────────────────────────────────────────
    logged_at = models.DateTimeField(
        db_index=True,
        verbose_name=_("Logged At"),
        help_text=_("Timestamp when the SLA breach was recorded server-side."),
    )

    class Meta:
        app_label = "common"
        db_table = "common_slow_performance_audit_log"
        ordering = ["-logged_at"]
        indexes = [
            models.Index(fields=["metric_name", "logged_at"], name="telemetry_metric_logged_idx"),
            models.Index(fields=["page_path", "logged_at"], name="telemetry_page_logged_idx"),
        ]
        verbose_name = _("Slow Performance Audit Log")
        verbose_name_plural = _("Slow Performance Audit Logs")

    def __str__(self) -> str:
        return (
            f"[{self.metric_name}={self.metric_value:.2f}] "
            f"on {self.page_path} @ {self.logged_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
