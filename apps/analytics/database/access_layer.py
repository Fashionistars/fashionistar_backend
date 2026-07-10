"""
Analytics database access layer.

Provides async-first analytics queries using Django 6.0 native async ORM.
This layer is consumed by apps.analytics workflows, tasks, and selectors.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


class AnalyticsDatabaseLayer:
    """
    Async database access layer for analytics queries.

    Methods follow the convention:
        - a<name> for async coroutines
        - get_<name> for sync helpers (used inside Celery tasks)
    """

    @staticmethod
    async def aget_recent_user_registrations(days: int = 30) -> int:
        """Return the number of users who joined in the last N days."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        since = timezone.now() - timedelta(days=days)
        return await User.objects.filter(date_joined__gte=since).acount()

    @staticmethod
    async def aget_active_user_count() -> int:
        """Return the number of active users."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        return await User.objects.filter(is_active=True).acount()

    @staticmethod
    def get_platform_order_stats(days: int = 30) -> dict[str, Any]:
        """Placeholder for platform order stats."""
        logger.info("[AnalyticsDatabaseLayer] get_platform_order_stats(days=%d)", days)
        return {}

    @staticmethod
    def get_trending_products(days: int = 30) -> list[dict[str, Any]]:
        """Placeholder for trending products."""
        logger.info("[AnalyticsDatabaseLayer] get_trending_products(days=%d)", days)
        return []

    @staticmethod
    def get_inventory_levels() -> dict[str, Any]:
        """Placeholder for inventory levels."""
        logger.info("[AnalyticsDatabaseLayer] get_inventory_levels()")
        return {}

    @staticmethod
    def get_all_vendor_stats() -> list[dict[str, Any]]:
        """Placeholder for vendor stats."""
        logger.info("[AnalyticsDatabaseLayer] get_all_vendor_stats()")
        return []
