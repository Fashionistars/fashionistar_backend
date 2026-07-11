"""
apps/analytics/services/query_builder.py
=========================================
SQL-free DSL query builder for safe, custom analytics reports.

Features:
  - Pre-defined query templates (revenue, orders, user engagement, vendor performance)
  - SQL-free DSL for safe query construction
  - Result pagination and CSV export
  - Query result caching with deterministic cache keys

Usage:
    from apps.analytics.services.query_builder import AnalyticsQueryBuilder

    builder = AnalyticsQueryBuilder()
    results = builder.execute(
        model="metric",
        filters={"name": "order_created", "metric_type": "counter"},
        aggregations={"avg_value": "avg", "total_count": "count"},
        group_by=["metric_type"],
        date_from="2026-01-01",
        date_to="2026-07-01",
    )
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from django.core.cache import cache
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.utils import timezone

from apps.analytics.models import (
    Alert,
    BusinessMetric,
    Metric,
    PerformanceMetric,
    UserActivity,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Allowed Fields per Model (Security Allowlist)
# ============================================================================

_ALLOWED_FIELDS: dict[str, dict[str, list[str]]] = {
    "metric": {
        "filter_fields": ["name", "metric_type", "value", "timestamp"],
        "group_by_fields": ["name", "metric_type"],
        "aggregation_fields": ["value", "id"],
    },
    "user_activity": {
        "filter_fields": ["action", "resource", "resource_id", "user_id", "timestamp"],
        "group_by_fields": ["action", "resource", "user_id"],
        "aggregation_fields": ["id", "resource_id"],
    },
    "performance_metric": {
        "filter_fields": ["endpoint", "method", "status_code", "response_time_ms", "timestamp"],
        "group_by_fields": ["endpoint", "method", "status_code"],
        "aggregation_fields": ["response_time_ms", "id"],
    },
    "business_metric": {
        "filter_fields": ["metric_name", "value", "period_start", "period_end", "created_at"],
        "group_by_fields": ["metric_name"],
        "aggregation_fields": ["value", "id"],
    },
    "alert": {
        "filter_fields": ["status", "severity", "fired_at", "resolved_at"],
        "group_by_fields": ["status", "severity"],
        "aggregation_fields": ["id", "metric_value"],
    },
}

_MODEL_MAP = {
    "metric": Metric,
    "user_activity": UserActivity,
    "performance_metric": PerformanceMetric,
    "business_metric": BusinessMetric,
    "alert": Alert,
}

_AGGREGATION_MAP = {
    "avg": Avg,
    "count": Count,
    "max": Max,
    "min": Min,
    "sum": Sum,
}


# ============================================================================
# Pre-defined Query Templates
# ============================================================================

QUERY_TEMPLATES: dict[str, dict[str, Any]] = {
    "revenue_summary": {
        "description": "Total revenue and average order value over a time period",
        "model": "business_metric",
        "filters": {"metric_name": "total_revenue"},
        "aggregations": {"total_revenue": "sum", "avg_revenue": "avg", "record_count": "count"},
        "group_by": [],
    },
    "order_metrics": {
        "description": "Order creation metrics grouped by metric type",
        "model": "metric",
        "filters": {"name__startswith": "order_"},
        "aggregations": {"avg_value": "avg", "total_count": "count"},
        "group_by": ["metric_type"],
    },
    "user_engagement": {
        "description": "User activity summary grouped by action type",
        "model": "user_activity",
        "filters": {},
        "aggregations": {"activity_count": "count"},
        "group_by": ["action"],
    },
    "vendor_performance": {
        "description": "Vendor performance metrics over time",
        "model": "business_metric",
        "filters": {"metric_name__startswith": "vendor_"},
        "aggregations": {"avg_value": "avg", "total_value": "sum"},
        "group_by": ["metric_name"],
    },
    "api_performance": {
        "description": "API endpoint performance summary",
        "model": "performance_metric",
        "filters": {},
        "aggregations": {
            "avg_response_time": "avg",
            "max_response_time": "max",
            "total_requests": "count",
        },
        "group_by": ["endpoint"],
    },
    "error_rate": {
        "description": "Error rate by endpoint (non-2xx responses)",
        "model": "performance_metric",
        "filters": {"status_code__gte": 400},
        "aggregations": {"error_count": "count"},
        "group_by": ["endpoint", "status_code"],
    },
    "alert_summary": {
        "description": "Alert summary by status and severity",
        "model": "alert",
        "filters": {},
        "aggregations": {"alert_count": "count"},
        "group_by": ["status", "severity"],
    },
}


# ============================================================================
# Query Builder
# ============================================================================

class AnalyticsQueryBuilder:
    """
    SQL-free DSL query builder for safe analytics queries.

    All queries are validated against an allowlist of fields to prevent
    SQL injection and unauthorized data access.
    """

    # Cache timeout for query results (5 minutes)
    CACHE_TIMEOUT = 300
    CACHE_PREFIX = "analytics:query:"

    # Max results per query
    MAX_RESULTS = 10000

    @classmethod
    def list_templates(cls) -> dict[str, str]:
        """Return available query templates with descriptions."""
        return {
            key: template["description"]
            for key, template in QUERY_TEMPLATES.items()
        }

    @classmethod
    def execute_template(
        cls,
        template_name: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute a pre-defined query template.

        Args:
            template_name: Name of the template to execute.
            date_from: Optional ISO date string for start of range.
            date_to: Optional ISO date string for end of range.

        Returns:
            dict: Query results with metadata.
        """
        template = QUERY_TEMPLATES.get(template_name)
        if not template:
            raise ValueError(f"Unknown template: {template_name}")

        return cls.execute(
            model=template["model"],
            filters=template.get("filters", {}),
            aggregations=template.get("aggregations", {}),
            group_by=template.get("group_by", []),
            date_from=date_from,
            date_to=date_to,
        )

    @classmethod
    def execute(
        cls,
        model: str,
        filters: Optional[dict[str, Any]] = None,
        aggregations: Optional[dict[str, str]] = None,
        group_by: Optional[list[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        order_by: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Execute a custom analytics query.

        Args:
            model: Model name (must be in _MODEL_MAP).
            filters: Dict of field → value filters (validated against allowlist).
            aggregations: Dict of alias → aggregation function (avg, count, max, min, sum).
            group_by: List of fields to group by.
            date_from: ISO date string for range start.
            date_to: ISO date string for range end.
            order_by: Field name to order by (prefix with - for descending).
            limit: Maximum number of results.

        Returns:
            dict: Query results with metadata.
        """
        # Validate model
        if model not in _MODEL_MAP:
            raise ValueError(f"Invalid model: {model}. Allowed: {list(_MODEL_MAP.keys())}")

        # Validate fields against allowlist
        allowed = _ALLOWED_FIELDS[model]
        filters = filters or {}
        aggregations = aggregations or {}
        group_by = group_by or []

        cls._validate_fields(filters.keys(), allowed["filter_fields"], "filter")
        cls._validate_fields(group_by, allowed["group_by_fields"], "group_by")

        for alias, agg_func in aggregations.items():
            if agg_func not in _AGGREGATION_MAP:
                raise ValueError(f"Invalid aggregation function: {agg_func}. Allowed: {list(_AGGREGATION_MAP.keys())}")

        # Build cache key
        cache_key = cls._build_cache_key(model, filters, aggregations, group_by, date_from, date_to, order_by, limit)
        cached = cache.get(cache_key)
        if cached:
            cached["cached"] = True
            return cached

        # Build queryset
        django_model = _MODEL_MAP[model]
        queryset = django_model.objects.all()

        # Apply date range filter
        date_field = cls._get_date_field(model)
        if date_from:
            dt_from = cls._parse_date(date_from)
            queryset = queryset.filter(**{f"{date_field}__gte": dt_from})
        if date_to:
            dt_to = cls._parse_date(date_to)
            queryset = queryset.filter(**{f"{date_field}__lte": dt_to})

        # Apply filters
        for field, value in filters.items():
            # Handle lookup suffixes (e.g., name__startswith)
            base_field = field.split("__")[0]
            if base_field not in allowed["filter_fields"]:
                raise ValueError(f"Field '{field}' is not allowed for filtering on '{model}'")
            queryset = queryset.filter(**{field: value})

        # Apply aggregations
        if aggregations:
            agg_kwargs = {}
            for alias, agg_func in aggregations.items():
                # Determine the field to aggregate on
                agg_field = cls._get_aggregation_field(model, alias, allowed["aggregation_fields"])
                agg_class = _AGGREGATION_MAP[agg_func]
                if agg_func == "count":
                    agg_kwargs[alias] = agg_class("id")
                else:
                    agg_kwargs[alias] = agg_class(agg_field)

            if group_by:
                # Group by with aggregations
                results = list(queryset.values(*group_by).annotate(**agg_kwargs))
            else:
                # Aggregate only (no group by)
                result = queryset.aggregate(**agg_kwargs)
                results = [result]
        else:
            # No aggregations — return raw records (limited)
            if group_by:
                results = list(queryset.values(*group_by).distinct()[:limit])
            else:
                # Return field values
                values_fields = allowed["filter_fields"]
                results = list(queryset.values(*values_fields)[:limit])

        # Apply ordering
        if order_by:
            base_order = order_by.lstrip("-")
            if base_order in allowed["filter_fields"] or base_order in aggregations:
                queryset = queryset.order_by(order_by)

        # Limit results
        if len(results) > cls.MAX_RESULTS:
            results = results[: cls.MAX_RESULTS]

        result_data = {
            "model": model,
            "filters": filters,
            "aggregations": aggregations,
            "group_by": group_by,
            "date_from": date_from,
            "date_to": date_to,
            "count": len(results),
            "results": results,
            "cached": False,
            "executed_at": timezone.now().isoformat(),
        }

        # Cache the results
        cache.set(cache_key, result_data, timeout=cls.CACHE_TIMEOUT)

        logger.info(
            "[AnalyticsQueryBuilder.execute] model=%s count=%d cached_key=%s",
            model,
            len(results),
            cache_key[:50],
        )
        return result_data

    @classmethod
    def export_csv(cls, query_result: dict[str, Any]) -> str:
        """
        Export query results as CSV string.

        Args:
            query_result: Result dict from execute() or execute_template().

        Returns:
            str: CSV-formatted string.
        """
        results = query_result.get("results", [])
        if not results:
            return ""

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=results[0].keys())
        writer.writeheader()
        for row in results:
            writer.writerow(row)

        return output.getvalue()

    # ========================================================================
    # Private Helpers
    # ========================================================================

    @classmethod
    def _validate_fields(cls, fields, allowed_fields: list[str], context: str) -> None:
        """Validate that all fields are in the allowlist."""
        for field in fields:
            base_field = field.split("__")[0]
            if base_field not in allowed_fields:
                raise ValueError(
                    f"Field '{field}' is not allowed for {context} on this model. "
                    f"Allowed fields: {allowed_fields}"
                )

    @classmethod
    def _build_cache_key(
        cls, model, filters, aggregations, group_by, date_from, date_to, order_by, limit
    ) -> str:
        """Build a deterministic cache key for the query."""
        key_data = json.dumps({
            "model": model,
            "filters": filters,
            "aggregations": aggregations,
            "group_by": group_by,
            "date_from": date_from,
            "date_to": date_to,
            "order_by": order_by,
            "limit": limit,
        }, sort_keys=True, default=str)
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        return f"{cls.CACHE_PREFIX}{key_hash}"

    @classmethod
    def _get_date_field(cls, model: str) -> str:
        """Get the primary date field for the model."""
        date_fields = {
            "metric": "timestamp",
            "user_activity": "timestamp",
            "performance_metric": "timestamp",
            "business_metric": "period_start",
            "alert": "fired_at",
        }
        return date_fields.get(model, "timestamp")

    @classmethod
    def _parse_date(cls, date_str: str) -> datetime:
        """Parse an ISO date string."""
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Invalid date format: {date_str}. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")

    @classmethod
    def _get_aggregation_field(cls, model: str, alias: str, allowed: list[str]) -> str:
        """Determine which field to aggregate on based on the alias."""
        # Try to infer from alias name
        if "value" in alias.lower() or "revenue" in alias.lower():
            if "value" in allowed:
                return "value"
        if "response_time" in alias.lower():
            return "response_time_ms"
        if "count" in alias.lower():
            return "id"
        # Default to first allowed aggregation field
        return allowed[0] if allowed else "id"
