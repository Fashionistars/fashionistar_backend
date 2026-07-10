"""
apps/analytics/services/__init__.py
====================================
Master barrel for analytics services package.

Service classes are imported directly from services.services (the canonical
location after the Phase 7.2 migration from the legacy root-level services.py).

    from apps.analytics.services import AnalyticsService
    AnalyticsService.record_metric(name="order_created", value=1.0)

    # OR via domain-specific helpers:
    from apps.analytics.services import order_analytics
    metrics = order_analytics.get_order_metrics(days=30)
"""

from __future__ import annotations

from apps.analytics.services.services import (
    AnalyticsService,
    MetricsService,
    RealTimeAnalyticsService,
    ReportingService,
    realtime_analytics,
)

__all__ = [
    "AnalyticsService",
    "MetricsService",
    "RealTimeAnalyticsService",
    "ReportingService",
    "realtime_analytics",
]
