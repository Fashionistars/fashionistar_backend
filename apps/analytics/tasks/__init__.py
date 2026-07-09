"""
Analytics Celery tasks.

This module contains analytics-related Celery tasks for batch processing,
report generation, and data aggregation across all 27 backend apps.
AI-specific tasks remain in apps/ai.
"""

from apps.analytics.tasks.analytics_tasks import (
    generate_daily_report,
    run_platform_analytics,
    run_product_performance_analysis,
    run_user_behavior_analysis,
)

__all__ = [
    "generate_daily_report",
    "run_platform_analytics",
    "run_product_performance_analysis",
    "run_user_behavior_analysis",
]
