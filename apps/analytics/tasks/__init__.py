"""
Analytics Celery tasks.

This module contains analytics-related Celery tasks for batch processing,
report generation, and data aggregation across all 27 backend apps.
AI-specific tasks remain in apps/ai.
"""

from apps.analytics.tasks.analytics_tasks import (
    cleanup_expired_data,
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
from apps.analytics.tasks.alert_evaluation_tasks import (
    evaluate_alert_rules,
)
from apps.analytics.tasks.cache_warming_tasks import (
    refresh_materialized_views,
    warm_capacity_cache,
    warm_dashboard_cache,
    warm_query_builder_cache,
)

__all__ = [
    "generate_daily_report",
    "run_platform_analytics",
    "run_product_performance_analysis",
    "run_realtime_analytics",
    "run_user_behavior_analysis",
    "run_vendor_analytics",
    "cleanup_expired_data",
    "rollup_1m",
    "rollup_5m",
    "rollup_1h",
    "rollup_1d",
    "evaluate_alert_rules",
    "warm_dashboard_cache",
    "refresh_materialized_views",
    "warm_query_builder_cache",
    "warm_capacity_cache",
]
