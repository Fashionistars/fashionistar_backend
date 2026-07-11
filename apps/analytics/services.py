"""
Deprecated shim — service classes have been migrated to
apps/analytics/services/services.py for proper package structure.

This file is kept only for backward compatibility with any code that
references `apps.analytics.services` directly via relative import
(`from .services import ...`). It will be removed in a future cleanup phase.
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