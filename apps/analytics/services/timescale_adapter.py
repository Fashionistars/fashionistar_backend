"""
apps/analytics/services/timescale_adapter.py
=============================================
Dual-write adapter for TimescaleDB integration.

Routes new metric writes to both PostgreSQL (standard Django ORM)
and TimescaleDB (when available). Selectors can query TimescaleDB
for time-range filters with automatic fallback to PostgreSQL.

Usage:
    from apps.analytics.services.timescale_adapter import TimescaleAdapter

    # Write to both stores
    TimescaleAdapter.write_metric(name="order_created", value=1.0, metric_type="counter")

    # Query with TimescaleDB preference
    results = TimescaleAdapter.query_metrics(name="order_created", date_from=..., date_to=...)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from django.db import connection
from django.utils import timezone

from apps.analytics.database.timescale import TimescaleDB
from apps.analytics.models import Metric, PerformanceMetric

logger = logging.getLogger(__name__)


class TimescaleAdapter:
    """
    Dual-write adapter for TimescaleDB + PostgreSQL.

    Writes go to both stores (when TimescaleDB is available).
    Reads prefer TimescaleDB for time-range queries and fall back
    to standard Django ORM when TimescaleDB is unavailable.
    """

    @classmethod
    def write_metric(
        cls,
        name: str,
        value: float,
        metric_type: str = "gauge",
        tags: Optional[dict] = None,
        timestamp: Optional[datetime] = None,
    ) -> Metric:
        """
        Write a metric to both PostgreSQL and TimescaleDB.

        Args:
            name: Metric name.
            value: Metric value.
            metric_type: Metric type (counter, gauge, histogram, timer).
            tags: Optional categorization tags.
            timestamp: Optional timestamp (defaults to now).

        Returns:
            Metric: The created Django Metric instance.
        """
        timestamp = timestamp or timezone.now()

        # Always write to PostgreSQL (Django ORM)
        metric = Metric.objects.create(
            name=name,
            value=value,
            metric_type=metric_type,
            tags=tags or {},
            timestamp=timestamp,
        )

        # Dual-write to TimescaleDB (if available)
        if TimescaleDB.is_available():
            try:
                with connection.cursor() as cursor:
                    import json

                    cursor.execute(
                        "INSERT INTO analytics_metric (name, metric_type, value, tags, timestamp) "
                        "VALUES (%s, %s, %s, %s, %s);",
                        [name, metric_type, value, json.dumps(tags or {}), timestamp],
                    )
            except Exception as exc:
                logger.error("[TimescaleAdapter.write_metric] TimescaleDB write failed: %s", exc)
                # Don't fail the request — PostgreSQL write already succeeded

        return metric

    @classmethod
    def query_metrics(
        cls,
        name: Optional[str] = None,
        metric_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Query metrics with TimescaleDB preference and PostgreSQL fallback.

        Args:
            name: Filter by metric name.
            metric_type: Filter by metric type.
            date_from: Start of date range.
            date_to: End of date range.
            limit: Maximum number of results.

        Returns:
            list[dict]: Metric records as dicts.
        """
        if TimescaleDB.is_available():
            return cls._query_timescale(name, metric_type, date_from, date_to, limit)
        return cls._query_postgres(name, metric_type, date_from, date_to, limit)

    @classmethod
    def _query_timescale(
        cls,
        name: Optional[str],
        metric_type: Optional[str],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query metrics from TimescaleDB with time_bucket optimization."""
        try:
            with connection.cursor() as cursor:
                query = "SELECT id, name, metric_type, value, tags, timestamp FROM analytics_metric WHERE 1=1"
                params = []

                if name:
                    query += " AND name = %s"
                    params.append(name)
                if metric_type:
                    query += " AND metric_type = %s"
                    params.append(metric_type)
                if date_from:
                    query += " AND timestamp >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND timestamp <= %s"
                    params.append(date_to)

                query += " ORDER BY timestamp DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, params)
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

                import json

                results = []
                for row in rows:
                    record = dict(zip(columns, row))
                    if isinstance(record.get("tags"), str):
                        record["tags"] = json.loads(record["tags"])
                    if isinstance(record.get("timestamp"), str):
                        record["timestamp"] = record["timestamp"]
                    results.append(record)

                return results
        except Exception as exc:
            logger.error("[TimescaleAdapter._query_timescale] Failed, falling back to PostgreSQL: %s", exc)
            return cls._query_postgres(name, metric_type, date_from, date_to, limit)

    @classmethod
    def _query_postgres(
        cls,
        name: Optional[str],
        metric_type: Optional[str],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query metrics from PostgreSQL via Django ORM (fallback)."""
        queryset = Metric.objects.all()
        if name:
            queryset = queryset.filter(name=name)
        if metric_type:
            queryset = queryset.filter(metric_type=metric_type)
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)

        metrics = queryset.order_by("-timestamp")[:limit]
        return [
            {
                "id": m.id,
                "name": m.name,
                "metric_type": m.metric_type,
                "value": m.value,
                "tags": m.tags,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in metrics
        ]

    @classmethod
    def backfill_historical_data(cls, batch_size: int = 5000) -> dict[str, Any]:
        """
        Backfill historical Metric data from PostgreSQL to TimescaleDB.

        Args:
            batch_size: Number of records to backfill per batch.

        Returns:
            dict: Backfill statistics.
        """
        if not TimescaleDB.is_available():
            return {"status": "skipped", "reason": "TimescaleDB not available"}

        import json

        total_migrated = 0
        errors = 0

        queryset = Metric.objects.all().order_by("timestamp")
        total_count = queryset.count()

        for offset in range(0, total_count, batch_size):
            batch = queryset[offset : offset + batch_size]
            try:
                with connection.cursor() as cursor:
                    values = [
                        (m.name, m.metric_type, m.value, json.dumps(m.tags), m.timestamp)
                        for m in batch
                    ]
                    cursor.executemany(
                        "INSERT INTO analytics_metric (name, metric_type, value, tags, timestamp) "
                        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;",
                        values,
                    )
                    total_migrated += len(values)
            except Exception as exc:
                logger.error("[TimescaleAdapter.backfill] Batch failed: %s", exc)
                errors += 1

        logger.info(
            "[TimescaleAdapter.backfill] Migrated %d/%d records (%d batch errors)",
            total_migrated,
            total_count,
            errors,
        )

        return {
            "status": "success" if errors == 0 else "partial",
            "total_records": total_count,
            "migrated": total_migrated,
            "batch_errors": errors,
        }
