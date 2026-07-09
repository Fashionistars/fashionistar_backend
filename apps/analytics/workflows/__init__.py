"""
Analytics workflow orchestration.

This module contains analytics workflows that orchestrate data aggregation
and insight generation across all 27 backend apps. AI-specific workflows
(recommendation, measurement, ingestion) remain in apps/ai.
"""

from apps.analytics.workflows.analytics import AnalyticsWorkflow
from apps.analytics.workflows.user_behavior import UserBehaviorWorkflow
from apps.analytics.workflows.product_performance import ProductPerformanceWorkflow
from apps.analytics.workflows.vendor_performance import VendorPerformanceWorkflow

__all__ = [
    "AnalyticsWorkflow",
    "UserBehaviorWorkflow",
    "ProductPerformanceWorkflow",
    "VendorPerformanceWorkflow",
]
