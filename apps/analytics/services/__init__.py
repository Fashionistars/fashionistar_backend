"""
apps/analytics/services/__init__.py
====================================
Master barrel for analytics services package.

Domain analytics helpers are exposed as lazily-imported submodules to prevent
circular import chains during django.setup(). Import the specific module
you need directly:

    from apps.analytics.services import AnalyticsService
    AnalyticsService.record_metric(name="order_created", value=1.0)

    # OR via domain-specific helpers:
    from apps.analytics.services import order_analytics
    metrics = order_analytics.get_order_metrics(days=30)

Design:
    Shared analytics services are exposed via Python's ``__getattr__`` hook
    so they are only imported on first access. App-specific analytics live
    in sub-packages named after each backend app (mirroring apps/audit_logs).
"""

from __future__ import annotations

__all__ = ["AnalyticsService", "RealTimeAnalyticsService"]


def __getattr__(name: str):
    """Lazy-import gateway — keeps django.setup() safe from circular imports."""
    if name == "AnalyticsService":
        from apps.analytics.services.services import AnalyticsService  # noqa: PLC0415
        return AnalyticsService
    if name == "RealTimeAnalyticsService":
        from apps.analytics.services.services import RealTimeAnalyticsService  # noqa: PLC0415
        return RealTimeAnalyticsService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
