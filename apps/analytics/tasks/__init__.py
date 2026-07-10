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
    run_realtime_analytics,
    run_user_behavior_analysis,
    run_vendor_analytics,
)
from apps.analytics.tasks.aggregation_tasks import (
    rollup_1d,
    rollup_1h,
    rollup_1m,
    rollup_5m,
)

__all__ = [
    "generate_daily_report",
    "run_platform_analytics",
    "run_product_performance_analysis",
    "run_realtime_analytics",
    "run_user_behavior_analysis",
    "run_vendor_analytics",
    "rollup_1m",
    "rollup_5m",
    "rollup_1h",
    "rollup_1d",
]
