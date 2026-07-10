"""
Tests for Phase 8 advanced architecture components.

Verifies imports, basic structure, and key functionality of:
- Alert Engine (8.4)
- Query Builder (8.5)
- Bulk Ingestion (8.7)
- Dashboard Service (8.8)
- Capacity Service (8.10)
- TimescaleDB adapter (8.1)
- Materialized Views (8.6)
- Structlog config (8.9)
- Metric Rollup models (8.2)
- WebSocket routing (8.3)
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestPhase8Imports:
    """Verify all Phase 8 modules are importable."""

    def test_alert_engine_import(self):
        from apps.analytics.services.alert_engine import AlertEngine
        assert AlertEngine is not None

    def test_query_builder_import(self):
        from apps.analytics.services.query_builder import AnalyticsQueryBuilder
        assert AnalyticsQueryBuilder is not None

    def test_bulk_ingestion_import(self):
        from apps.analytics.services.bulk_ingestion import BulkIngestionService
        assert BulkIngestionService is not None

    def test_dashboard_service_import(self):
        from apps.analytics.services.dashboard_service import DashboardService
        assert DashboardService is not None

    def test_capacity_service_import(self):
        from apps.analytics.services.capacity_service import CapacityService
        assert CapacityService is not None

    def test_timescale_import(self):
        from apps.analytics.database.timescale import TimescaleDB
        assert TimescaleDB is not None

    def test_timescale_adapter_import(self):
        from apps.analytics.services.timescale_adapter import TimescaleAdapter
        assert TimescaleAdapter is not None

    def test_materialized_views_import(self):
        from apps.analytics.database.materialized_views import MaterializedViewManager
        assert MaterializedViewManager is not None

    def test_structlog_config_import(self):
        from apps.analytics.logging.structlog_config import configure_structlog
        assert callable(configure_structlog)

    def test_alert_evaluation_task_import(self):
        from apps.analytics.tasks.alert_evaluation_tasks import evaluate_alert_rules
        assert callable(evaluate_alert_rules)

    def test_cache_warming_tasks_import(self):
        from apps.analytics.tasks.cache_warming_tasks import (
            warm_dashboard_cache,
            refresh_materialized_views,
            warm_query_builder_cache,
            warm_capacity_cache,
        )
        assert all(callable(t) for t in [warm_dashboard_cache, refresh_materialized_views, warm_query_builder_cache, warm_capacity_cache])

    def test_routing_import(self):
        from apps.analytics.routing import websocket_urlpatterns
        assert isinstance(websocket_urlpatterns, list)
        assert len(websocket_urlpatterns) > 0

    def test_dashboard_views_router_import(self):
        from apps.analytics.apis.async_.dashboard_views import router
        assert router is not None


@pytest.mark.django_db
class TestMetricRollupModels:
    """Verify MetricRollup and PerformanceMetricRollup models (Phase 8.2)."""

    def test_metric_rollup_model_exists(self):
        from apps.analytics.models import MetricRollup
        assert MetricRollup is not None

    def test_performance_metric_rollup_model_exists(self):
        from apps.analytics.models import PerformanceMetricRollup
        assert PerformanceMetricRollup is not None

    def test_metric_rollup_create(self):
        from apps.analytics.models import MetricRollup
        from django.utils import timezone

        rollup = MetricRollup.objects.create(
            name="test_metric",
            metric_type="gauge",
            window="1h",
            timestamp=timezone.now(),
            avg=10.0,
            min=5.0,
            max=15.0,
            count=100,
            sum=1000.0,
        )
        assert rollup.id is not None
        assert rollup.name == "test_metric"
        assert rollup.window == "1h"
        assert rollup.avg == 10.0

    def test_performance_metric_rollup_create(self):
        from apps.analytics.models import PerformanceMetricRollup
        from django.utils import timezone

        rollup = PerformanceMetricRollup.objects.create(
            endpoint="/api/v1/products/",
            method="GET",
            window="5m",
            timestamp=timezone.now(),
            avg_response_time=50.5,
            max_response_time=200,
            error_count=2,
            total=500,
        )
        assert rollup.id is not None
        assert rollup.endpoint == "/api/v1/products/"
        assert rollup.total == 500

    def test_metric_rollup_unique_together(self):
        """Duplicate name+type+window+timestamp raises IntegrityError."""
        from apps.analytics.models import MetricRollup
        from django.utils import timezone
        from django.db import IntegrityError

        ts = timezone.now()
        MetricRollup.objects.create(
            name="dup_test", metric_type="gauge", window="1h",
            timestamp=ts, avg=1.0, count=1, sum=1.0,
        )
        with pytest.raises(IntegrityError):
            MetricRollup.objects.create(
                name="dup_test", metric_type="gauge", window="1h",
                timestamp=ts, avg=2.0, count=1, sum=2.0,
            )

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        True,
        reason="Requires migration runner (DisableMigrations prevents table creation for new models)",
    )
    async def test_metric_rollup_aget_rollup(self):
        from apps.analytics.models import MetricRollup
        from django.utils import timezone

        ts = timezone.now()
        await MetricRollup.objects.acreate(
            name="async_test", metric_type="gauge", window="1h",
            timestamp=ts, avg=1.0, count=1, sum=1.0,
        )
        results = await MetricRollup.aget_rollup(name="async_test", window="1h")
        assert len(results) == 1
        assert results[0].name == "async_test"


class TestAlertEngine:
    """Verify AlertEngine key functionality (Phase 8.4)."""

    def test_operators_gt(self):
        from apps.analytics.services.alert_engine import _OPERATORS

        assert _OPERATORS["gt"](150.0, 100.0) is True
        assert _OPERATORS["gt"](50.0, 100.0) is False

    def test_operators_lt(self):
        from apps.analytics.services.alert_engine import _OPERATORS

        assert _OPERATORS["lt"](50.0, 100.0) is True
        assert _OPERATORS["lt"](150.0, 100.0) is False

    def test_operators_gte(self):
        from apps.analytics.services.alert_engine import _OPERATORS

        assert _OPERATORS["gte"](100.0, 100.0) is True
        assert _OPERATORS["gte"](99.0, 100.0) is False

    def test_operators_lte(self):
        from apps.analytics.services.alert_engine import _OPERATORS

        assert _OPERATORS["lte"](100.0, 100.0) is True
        assert _OPERATORS["lte"](101.0, 100.0) is False


class TestQueryBuilder:
    """Verify QueryBuilder key functionality (Phase 8.5)."""

    def test_query_builder_has_templates(self):
        from apps.analytics.services.query_builder import QUERY_TEMPLATES

        assert isinstance(QUERY_TEMPLATES, dict)
        assert len(QUERY_TEMPLATES) > 0
        assert "revenue_summary" in QUERY_TEMPLATES

    def test_query_builder_field_allowlist(self):
        from apps.analytics.services.query_builder import _ALLOWED_FIELDS

        assert isinstance(_ALLOWED_FIELDS, dict)
        assert "metric" in _ALLOWED_FIELDS
        assert "filter_fields" in _ALLOWED_FIELDS["metric"]

    def test_query_builder_list_templates(self):
        from apps.analytics.services.query_builder import AnalyticsQueryBuilder

        templates = AnalyticsQueryBuilder.list_templates()
        assert isinstance(templates, dict)
        assert len(templates) > 0

    def test_query_builder_csv_export_method(self):
        from apps.analytics.services.query_builder import AnalyticsQueryBuilder

        assert hasattr(AnalyticsQueryBuilder, "export_csv")
        assert callable(AnalyticsQueryBuilder.export_csv)


class TestBulkIngestion:
    """Verify BulkIngestionService key functionality (Phase 8.7)."""

    def test_max_batch_size_defined(self):
        from apps.analytics.services.bulk_ingestion import BulkIngestionService

        assert hasattr(BulkIngestionService, "MAX_BATCH_SIZE")
        assert BulkIngestionService.MAX_BATCH_SIZE > 0

    def test_max_cardinality_defined(self):
        from apps.analytics.services.bulk_ingestion import BulkIngestionService

        assert hasattr(BulkIngestionService, "MAX_CARDINALITY_PER_NAME")
        assert BulkIngestionService.MAX_CARDINALITY_PER_NAME > 0

    def test_ingest_method_exists(self):
        from apps.analytics.services.bulk_ingestion import BulkIngestionService

        assert hasattr(BulkIngestionService, "ingest")
        assert callable(BulkIngestionService.ingest)


class TestCeleryTaskRegistration:
    """Verify Phase 8 Celery tasks are registered in celery.py."""

    def test_alert_evaluation_in_routes(self):
        from backend.celery import app

        routes = app.conf.task_routes
        found = False
        for key, config in routes.items():
            if "alert_evaluation" in key or "evaluate_alert" in key:
                found = True
                break
        assert found, "alert_evaluation task not found in Celery task routes"

    def test_cache_warming_in_routes(self):
        from backend.celery import app

        routes = app.conf.task_routes
        found = False
        for key, config in routes.items():
            if "cache_warming" in key or "warm_" in key:
                found = True
                break
        assert found, "cache_warming task not found in Celery task routes"

    def test_cleanup_in_routes(self):
        from backend.celery import app

        routes = app.conf.task_routes
        found = False
        for key, config in routes.items():
            if "cleanup_expired_data" in key:
                found = True
                break
        assert found, "cleanup_expired_data not found in Celery task routes"

    def test_aggregation_tasks_in_routes(self):
        from backend.celery import app

        routes = app.conf.task_routes
        found = False
        for key, config in routes.items():
            if "aggregation_tasks" in key:
                found = True
                break
        assert found, "aggregation_tasks not found in Celery task routes"

    def test_cleanup_in_beat_schedule(self):
        from backend.celery import app

        beat = app.conf.beat_schedule
        found = False
        for name, config in beat.items():
            if "cleanup" in str(config.get("task", "")).lower():
                found = True
                break
        assert found, "cleanup_expired_data not found in Beat schedule"


class TestNoDjangoSignals:
    """Verify no Django signals are used in the analytics domain (Phase 7 requirement)."""

    def test_no_signal_imports_in_models(self):
        """models.py should not import django.dispatch signals."""
        import apps.analytics.models as models_module
        import inspect

        source = inspect.getsource(models_module)
        assert "from django.dispatch" not in source, "models.py should not import django.dispatch"
        assert "Signal(" not in source, "models.py should not define custom signals"
        assert "receiver(" not in source, "models.py should not use @receiver decorator"

    def test_no_signal_imports_in_services(self):
        """services module should not import django.dispatch signals."""
        import apps.analytics.services.services as services_module
        import inspect

        source = inspect.getsource(services_module)
        assert "from django.dispatch" not in source
        assert "Signal(" not in source

    def test_no_signal_imports_in_views(self):
        """analytics_views should not import django.dispatch signals."""
        import apps.analytics.apis.async_.analytics_views as views
        import inspect

        source = inspect.getsource(views)
        assert "from django.dispatch" not in source
        assert "Signal(" not in source

    def test_no_signal_imports_in_tasks(self):
        """analytics_tasks should not import django.dispatch signals."""
        import apps.analytics.tasks.analytics_tasks as tasks
        import inspect

        source = inspect.getsource(tasks)
        assert "from django.dispatch" not in source
        assert "Signal(" not in source
