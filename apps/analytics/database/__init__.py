"""
Analytics database access layer.

This module provides async database access methods for analytics queries,
following Django 6.0 native async ORM patterns.
"""

from apps.analytics.database.access_layer import AnalyticsDatabaseLayer

__all__ = [
    "AnalyticsDatabaseLayer",
]
