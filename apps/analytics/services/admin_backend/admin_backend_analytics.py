"""
Admin backend analytics service.

Place app-specific analytics selectors, services and helpers here.
"""

from __future__ import annotations


def get_admin_backend_metrics(days: int = 30) -> dict:
    """
    Return analytics metrics for the admin_backend domain.

    Args:
        days: Lookback window in days.

    Returns:
        dict: Aggregated metrics for admin_backend.
    """
    return {}
