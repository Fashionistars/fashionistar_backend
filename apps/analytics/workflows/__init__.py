"""
Analytics workflow orchestration.

This module contains analytics workflows that orchestrate data aggregation
and insight generation across all 27 backend apps. AI-specific workflows
(recommendation, measurement, ingestion) remain in apps/ai.
"""

from apps.analytics.workflows.analytics import AnalyticsWorkflow

__all__ = [
    "AnalyticsWorkflow",
]
