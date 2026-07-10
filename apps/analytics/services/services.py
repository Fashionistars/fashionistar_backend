"""
Deprecated shim — apps/analytics/services/__init__.py now loads the legacy
apps/analytics/services.py module directly. This file is kept only to avoid
import errors in case any external code references it; it will be removed in
the cleanup phase.
"""

from __future__ import annotations

from apps.analytics.services import AnalyticsService, RealTimeAnalyticsService

__all__ = ["AnalyticsService", "RealTimeAnalyticsService"]

