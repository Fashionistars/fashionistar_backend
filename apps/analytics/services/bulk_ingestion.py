"""
apps/analytics/services/bulk_ingestion.py
==========================================
High-volume metric ingestion service with batching, validation, and
cardinality limits.

Features:
  - Accepts up to 1000 metrics per request
  - Cardinality limits reject new tag combinations beyond threshold
  - Batched bulk_create for efficient DB writes
  - Buffering to Redis Streams before persistence (optional)
  - Single audit log entry per batch

Usage:
    from apps.analytics.services.bulk_ingestion import BulkIngestionService

    results = BulkIngestionService.ingest(metrics_data=[
        {"name": "order_created", "metric_type": "counter", "value": 1.0, "tags": {"source": "web"}},
        {"name": "page_view", "metric_type": "counter", "value": 1.0, "tags": {"page": "home"}},
    ])
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from apps.analytics.models import Metric

logger = logging.getLogger(__name__)


class BulkIngestionService:
    """
    High-volume metric ingestion with validation, batching, and cardinality limits.
    """

    # Maximum metrics per bulk request
    MAX_BATCH_SIZE = 1000

    # Maximum unique tag combinations per metric name (cardinality limit)
    MAX_CARDINALITY_PER_NAME = 10000

    # Batch size for bulk_create
    DB_BATCH_SIZE = 500

    @classmethod
    def ingest(cls, metrics_data: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Ingest a batch of metrics with validation and batching.

        Args:
            metrics_data: List of metric dicts. Each dict must have:
                - name (str): Metric name
                - metric_type (str): One of 'counter', 'gauge', 'histogram', 'timer'
                - value (float): Metric value
                - tags (dict, optional): Categorization tags

        Returns:
            dict: Summary of ingestion results.
        """
        if len(metrics_data) > cls.MAX_BATCH_SIZE:
            return {
                "status": "rejected",
                "error": f"Batch size {len(metrics_data)} exceeds maximum of {cls.MAX_BATCH_SIZE}",
                "accepted": 0,
                "rejected": len(metrics_data),
            }

        validated: list[Metric] = []
        rejected: list[dict[str, Any]] = []
        cardinality_cache: dict[str, set] = {}

        for idx, metric_data in enumerate(metrics_data):
            try:
                cls._validate_metric(metric_data)

                # Check cardinality
                name = metric_data["name"]
                tags = metric_data.get("tags", {})
                tag_key = frozenset(tags.items()) if tags else frozenset()

                if name not in cardinality_cache:
                    cardinality_cache[name] = set()

                if tag_key not in cardinality_cache[name]:
                    # Check if we've exceeded cardinality for this name
                    existing_count = Metric.objects.filter(name=name).values("tags").distinct().count()
                    if existing_count >= cls.MAX_CARDINALITY_PER_NAME:
                        rejected.append({
                            "index": idx,
                            "name": name,
                            "error": f"Cardinality limit exceeded for metric '{name}' (max {cls.MAX_CARDINALITY_PER_NAME})",
                        })
                        continue
                    cardinality_cache[name].add(tag_key)

                # Create Metric instance (not saved yet)
                metric = Metric(
                    name=name,
                    metric_type=metric_data.get("metric_type", "gauge"),
                    value=float(metric_data["value"]),
                    tags=tags,
                    timestamp=timezone.now(),
                )
                validated.append(metric)

            except Exception as exc:
                rejected.append({
                    "index": idx,
                    "name": metric_data.get("name", "unknown"),
                    "error": str(exc),
                })

        # Batch bulk_create
        created_count = 0
        if validated:
            for i in range(0, len(validated), cls.DB_BATCH_SIZE):
                batch = validated[i : i + cls.DB_BATCH_SIZE]
                try:
                    Metric.objects.bulk_create(batch)
                    created_count += len(batch)
                except Exception as exc:
                    logger.error("[BulkIngestionService.ingest] Batch create failed: %s", exc)
                    rejected.extend([
                        {"index": i + j, "name": m.name, "error": str(exc)}
                        for j, m in enumerate(batch)
                    ])

        # Single audit log for the batch
        if created_count > 0:
            try:
                from apps.audit_logs.services.analytics.analytics_audit import AnalyticsAuditService

                AnalyticsAuditService.log_metric_recorded(
                    actor=None,
                    metric=None,
                    metadata={
                        "bulk_ingestion": True,
                        "count": created_count,
                        "metric_names": list({m.name for m in validated}),
                    },
                )
            except Exception as exc:
                logger.error("[BulkIngestionService.ingest] Audit log failed: %s", exc)

        result = {
            "status": "success" if not rejected else "partial",
            "accepted": created_count,
            "rejected": len(rejected),
            "total": len(metrics_data),
            "rejection_details": rejected[:50] if rejected else [],
        }

        logger.info(
            "[BulkIngestionService.ingest] Accepted=%d Rejected=%d Total=%d",
            created_count,
            len(rejected),
            len(metrics_data),
        )
        return result

    @classmethod
    def ingest_to_redis_stream(
        cls,
        metrics_data: list[dict[str, Any]],
        stream_key: str = "analytics:ingestion:stream",
    ) -> dict[str, Any]:
        """
        Buffer metrics to a Redis Stream for async persistence.

        Args:
            metrics_data: List of metric dicts.
            stream_key: Redis Stream key to buffer to.

        Returns:
            dict: Summary of buffered metrics.
        """
        import json

        from django.core.cache import cache

        redis_client = cache._cache.get_client() if hasattr(cache, "_cache") else None

        if redis_client is None:
            # Fallback to direct ingestion
            logger.warning("[BulkIngestionService.ingest_to_redis_stream] Redis client unavailable, falling back to direct ingestion")
            return cls.ingest(metrics_data)

        buffered = 0
        rejected = 0

        for metric_data in metrics_data:
            try:
                cls._validate_metric(metric_data)
                redis_client.xadd(
                    stream_key,
                    {"data": json.dumps(metric_data, default=str)},
                    maxlen=100000,
                    approximate=True,
                )
                buffered += 1
            except Exception as exc:
                logger.error("[BulkIngestionService.ingest_to_redis_stream] Rejected: %s", exc)
                rejected += 1

        return {
            "status": "success" if not rejected else "partial",
            "buffered": buffered,
            "rejected": rejected,
            "total": len(metrics_data),
            "stream_key": stream_key,
        }

    @classmethod
    def _validate_metric(cls, metric_data: dict[str, Any]) -> None:
        """Validate a single metric dict."""
        if not isinstance(metric_data, dict):
            raise ValueError("Metric data must be a dict")

        if "name" not in metric_data or not metric_data["name"]:
            raise ValueError("Metric 'name' is required")

        if "value" not in metric_data:
            raise ValueError("Metric 'value' is required")

        try:
            float(metric_data["value"])
        except (TypeError, ValueError):
            raise ValueError(f"Metric 'value' must be numeric, got: {metric_data['value']}")

        valid_types = {"counter", "gauge", "histogram", "timer"}
        metric_type = metric_data.get("metric_type", "gauge")
        if metric_type not in valid_types:
            raise ValueError(f"Invalid metric_type '{metric_type}'. Allowed: {valid_types}")

        tags = metric_data.get("tags", {})
        if tags and not isinstance(tags, dict):
            raise ValueError("Metric 'tags' must be a dict")
