"""
Measurements analytics service.

Place app-specific analytics selectors, services and helpers here.
This package provides read-only analytics about measurement profiles.
It does NOT contain measurement processing logic, which remains in apps/ai.
"""

from __future__ import annotations


def get_measurements_metrics(days: int = 30) -> dict:
    """Return analytics metrics for the measurements domain."""
    return {}
