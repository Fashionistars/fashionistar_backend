# apps/analytics/services/metrics_service.py
"""
Lightweight Prometheus-compatible metrics registry for the analytics domain.

This service provides Counter, Gauge, and Histogram primitives and can render
metrics in the Prometheus text exposition format without requiring the
prometheus_client package. If prometheus_client is installed, its native types
are used where convenient.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


try:
    from prometheus_client import Counter as PromCounter, Gauge as PromGauge, Histogram as PromHistogram
except ImportError:  # pragma: no cover
    PromCounter = PromGauge = PromHistogram = None


@dataclass
class _MetricSeries:
    """Internal representation of a metric label series."""
    labels: Dict[str, str]
    value: float = 0.0
    count: int = 0
    sum_value: float = 0.0
    buckets: Dict[float, int] = field(default_factory=lambda: defaultdict(int))


class _BaseMetric:
    """Base class for registry-backed metrics."""

    def __init__(self, name: str, description: str, labelnames: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.labelnames = labelnames or []
        self.series: Dict[str, _MetricSeries] = {}
        self._prom_metric = None

    def _key(self, labels: Dict[str, str]) -> str:
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))

    def _get_series(self, labels: Dict[str, str]) -> _MetricSeries:
        for name in self.labelnames:
            labels.setdefault(name, "")
        key = self._key(labels)
        if key not in self.series:
            self.series[key] = _MetricSeries(labels=dict(labels))
        return self.series[key]


class Counter(_BaseMetric):
    """Counter metric that only increases."""

    def inc(self, labels: Optional[Dict[str, str]] = None, amount: float = 1.0):
        labels = labels or {}
        series = self._get_series(labels)
        series.value += amount
        series.count += 1
        if self._prom_metric is not None:
            if labels:
                self._prom_metric.labels(**labels).inc(amount)
            else:
                self._prom_metric.inc(amount)


class Gauge(_BaseMetric):
    """Gauge metric that can go up and down."""

    def set(self, labels: Optional[Dict[str, str]] = None, value: float = 0.0):
        labels = labels or {}
        series = self._get_series(labels)
        series.value = value
        if self._prom_metric is not None:
            if labels:
                self._prom_metric.labels(**labels).set(value)
            else:
                self._prom_metric.set(value)

    def inc(self, labels: Optional[Dict[str, str]] = None, amount: float = 1.0):
        labels = labels or {}
        series = self._get_series(labels)
        series.value += amount
        if self._prom_metric is not None:
            if labels:
                self._prom_metric.labels(**labels).inc(amount)
            else:
                self._prom_metric.inc(amount)


class Histogram(_BaseMetric):
    """Histogram metric with configurable buckets."""

    def __init__(
        self,
        name: str,
        description: str,
        labelnames: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None,
    ):
        super().__init__(name, description, labelnames)
        self.buckets = sorted(buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
        self.buckets.append(float("inf"))

    def observe(self, labels: Optional[Dict[str, str]] = None, value: float = 0.0):
        labels = labels or {}
        series = self._get_series(labels)
        series.count += 1
        series.sum_value += value
        for bucket in self.buckets:
            if value <= bucket:
                series.buckets[bucket] += 1


class AnalyticsMetricsService:
    """
    Central metrics registry for analytics domain.

    Tracks ingestion rates, query performance, aggregation throughput, and
    error rates in a format compatible with Prometheus scraping.
    """

    _instance: Optional["AnalyticsMetricsService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_registry()
        return cls._instance

    def _init_registry(self):
        self.metrics: Dict[str, _BaseMetric] = {}
        self._register(
            Counter(
                "analytics_metric_ingested_total",
                "Total analytics metrics ingested",
                labelnames=["metric_type", "name"],
            )
        )
        self._register(
            Counter(
                "analytics_query_executed_total",
                "Total analytics queries executed",
                labelnames=["query_type"],
            )
        )
        self._register(
            Histogram(
                "analytics_query_duration_seconds",
                "Analytics query duration in seconds",
                labelnames=["query_type"],
                buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
            )
        )
        self._register(
            Counter(
                "analytics_aggregation_runs_total",
                "Total aggregation task executions",
                labelnames=["window"],
            )
        )
        self._register(
            Gauge(
                "analytics_rollup_cache_hit_ratio",
                "Cache hit ratio for analytics rollup queries",
                labelnames=["window"],
            )
        )
        self._register(
            Counter(
                "analytics_errors_total",
                "Total analytics domain errors",
                labelnames=["source"],
            )
        )
        self._register(
            Gauge(
                "analytics_realtime_events_active",
                "Number of active real-time analytics consumers",
                labelnames=[],
            )
        )

    def _register(self, metric: _BaseMetric):
        self.metrics[metric.name] = metric

    def record_metric_ingested(self, metric_type: str = "gauge", name: str = "unknown"):
        self.metrics["analytics_metric_ingested_total"].inc(
            labels={"metric_type": metric_type, "name": name}
        )

    def record_query(self, query_type: str, duration_seconds: float):
        self.metrics["analytics_query_executed_total"].inc(labels={"query_type": query_type})
        self.metrics["analytics_query_duration_seconds"].observe(
            labels={"query_type": query_type}, value=duration_seconds
        )

    def record_aggregation(self, window: str):
        self.metrics["analytics_aggregation_runs_total"].inc(labels={"window": window})

    def record_error(self, source: str):
        self.metrics["analytics_errors_total"].inc(labels={"source": source})

    def set_rollup_cache_hit_ratio(self, window: str, ratio: float):
        self.metrics["analytics_rollup_cache_hit_ratio"].set(
            labels={"window": window}, value=ratio
        )

    def set_realtime_consumers(self, count: int):
        self.metrics["analytics_realtime_events_active"].set(value=float(count))

    def render_prometheus(self) -> str:
        """Render all registered metrics in Prometheus text exposition format."""
        lines: List[str] = []
        for metric in self.metrics.values():
            lines.append(f"# HELP {metric.name} {metric.description}")
            lines.append(f"# TYPE {metric.name} {self._type(metric)}")
            for key, series in metric.series.items():
                label_str = ""
                if series.labels:
                    label_str = "{" + ",".join(
                        f'{k}="{v}"' for k, v in sorted(series.labels.items())
                    ) + "}"
                if isinstance(metric, Histogram):
                    for bucket in metric.buckets:
                        bucket_str = "+Inf" if bucket == float("inf") else str(bucket)
                        lines.append(
                            f'{metric.name}_bucket{{le="{bucket_str}"{self._append_labels(label_str)}}} {series.buckets.get(bucket, 0)}'
                        )
                    lines.append(
                        f"{metric.name}_sum{label_str} {series.sum_value}"
                    )
                    lines.append(
                        f"{metric.name}_count{label_str} {series.count}"
                    )
                else:
                    lines.append(f"{metric.name}{label_str} {series.value}")
        return "\n".join(lines)

    @staticmethod
    def _type(metric: _BaseMetric) -> str:
        if isinstance(metric, Counter):
            return "counter"
        if isinstance(metric, Gauge):
            return "gauge"
        if isinstance(metric, Histogram):
            return "histogram"
        return "gauge"

    @staticmethod
    def _append_labels(label_str: str) -> str:
        if not label_str:
            return ""
        return "," + label_str.strip("{}")


# Singleton accessor
def get_metrics_service() -> AnalyticsMetricsService:
    return AnalyticsMetricsService()
