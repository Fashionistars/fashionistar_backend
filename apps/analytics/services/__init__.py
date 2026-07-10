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

import importlib.util
import os
from types import ModuleType

__all__ = ["AnalyticsService", "RealTimeAnalyticsService"]


__legacy_services_module: ModuleType | None = None


def _load_legacy_services() -> ModuleType:
    """Load the legacy apps/analytics/services.py module by filesystem path.

    The legacy module uses relative imports (``from .models import ...``). We
    set its ``__package__`` to ``apps.analytics`` so those relative imports
    resolve correctly even though the module is executed under a temporary name.
    """
    global __legacy_services_module
    if __legacy_services_module is not None:
        return __legacy_services_module

    legacy_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "services.py",
    )
    spec = importlib.util.spec_from_file_location(
        "_legacy_analytics_services",
        legacy_path,
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "apps.analytics"
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    __legacy_services_module = module
    return module


def __getattr__(name: str):
    """Lazy-import gateway — keeps django.setup() safe from circular imports."""
    if name in __all__:
        module = _load_legacy_services()
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
