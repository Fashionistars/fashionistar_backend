"""
Tests for apps.analytics.services.metrics_service.
"""
from __future__ import annotations

import pytest

from apps.analytics.services.metrics_service import AnalyticsMetricsService, Counter, Gauge, Histogram


@pytest.mark.django_db
def test_counter_increments():
    """Counter metric should increment."""
    counter = Counter("test_counter", "Test counter", labelnames=["kind"])
    counter.inc(labels={"kind": "a"}, amount=2.0)
    counter.inc(labels={"kind": "a"})

    series = counter.series[counter._key({"kind": "a"})]
    assert series.value == 3.0


@pytest.mark.django_db
def test_gauge_set_and_inc():
    """Gauge metric should set and increment."""
    gauge = Gauge("test_gauge", "Test gauge", labelnames=["env"])
    gauge.set(labels={"env": "prod"}, value=10.0)
    gauge.inc(labels={"env": "prod"}, amount=5.0)

    series = gauge.series[gauge._key({"env": "prod"})]
    assert series.value == 15.0


@pytest.mark.django_db
def test_histogram_tracks_buckets():
    """Histogram metric should track bucket counts and sum."""
    histogram = Histogram("test_histogram", "Test histogram", buckets=[0.1, 1.0])
    histogram.observe(value=0.05)
    histogram.observe(value=0.5)
    histogram.observe(value=5.0)

    series = histogram.series[histogram._key({})]
    assert series.count == 3
    assert series.sum_value == pytest.approx(5.55, 0.01)
    assert series.buckets[0.1] == 1
    assert series.buckets[1.0] == 2


@pytest.mark.django_db
def test_metrics_service_render_prometheus():
    """Metrics service should render metrics in Prometheus exposition format."""
    service = AnalyticsMetricsService()
    service.record_metric_ingested(metric_type="gauge", name="m1")
    service.record_query(query_type="dashboard", duration_seconds=0.05)
    rendered = service.render_prometheus()

    assert "analytics_metric_ingested_total" in rendered
    assert "analytics_query_executed_total" in rendered
    assert "# TYPE" in rendered
