# apps/analytics/apis/async_/analytics_views.py
"""
Django Ninja async views for Analytics domain.
Follows vendor pattern with async endpoints under /api/v1/ninja/analytics/.
"""

import json
from datetime import timedelta
from typing import List, Optional

from django.core.cache import cache
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError
from pydantic import BaseModel

from apps.analytics.selectors.analytics_selectors import (
    aget_alerts,
    aget_analytics_dashboard_parallel,
    aget_business_metrics,
    aget_metrics,
    aget_performance_metrics,
    aget_user_activity,
)
from apps.analytics.services import AnalyticsService
from apps.audit_logs.services.analytics.analytics_audit import AnalyticsAuditService


router = Router(tags=['Analytics'])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class MetricSchema(BaseModel):
    id: int
    name: str
    metric_type: str
    value: float
    tags: dict
    timestamp: str


class UserActivitySchema(BaseModel):
    id: int
    action: str
    resource: str
    resource_id: Optional[int]
    timestamp: str


class PerformanceMetricSchema(BaseModel):
    id: int
    endpoint: str
    method: str
    response_time_ms: int
    status_code: int
    timestamp: str


class BusinessMetricSchema(BaseModel):
    id: int
    metric_name: str
    value: float
    period_start: str
    period_end: str
    created_at: str


class AlertSchema(BaseModel):
    id: int
    rule_name: str
    status: str
    metric_value: float
    message: str
    fired_at: str


class DashboardResponse(BaseModel):
    performance_count: int
    business_count: int
    alert_count: int
    activity_count: int
    avg_response_time_ms: float


class HealthCheckResponse(BaseModel):
    service: str
    status: str
    response_time_ms: float
    checks: list


class PrometheusMetricsResponse(BaseModel):
    metrics: str


class CreateMetricRequest(BaseModel):
    name: str
    metric_type: str
    value: float
    tags: Optional[dict] = None


class MetricCreatedResponse(BaseModel):
    id: int
    name: str
    metric_type: str
    value: float
    timestamp: str


class CreateBusinessMetricRequest(BaseModel):
    metric_name: str
    value: float
    period_start: str
    period_end: str


class BusinessMetricCreatedResponse(BaseModel):
    id: int
    metric_name: str
    value: float
    period_start: str
    period_end: str
    created_at: str


class ResolveAlertRequest(BaseModel):
    resolution_notes: Optional[str] = None


class AlertResolvedResponse(BaseModel):
    id: int
    status: str
    resolved_at: str
    message: str


class AnalyticsReportSchema(BaseModel):
    generated_at:    str
    days:            int
    scope:           str
    order_metrics:   dict = {}
    product_metrics: dict = {}
    user_metrics:    dict = {}
    vendor_metrics:  dict = {}
    anomalies:       list = []
    llm_insights:    str  = ""


# ============================================================================
# Async Endpoints
# ============================================================================

@router.get('/dashboard/', response=DashboardResponse)
async def get_analytics_dashboard(request: HttpRequest):
    """
    Get analytics dashboard data in parallel (async).
    Endpoint: GET /api/v1/ninja/analytics/dashboard/
    """
    user = request.auth
    user_id = str(user.id) if user else None
    
    dashboard_data = await aget_analytics_dashboard_parallel(user_id)
    
    # Log audit event
    AnalyticsAuditService.log_dashboard_viewed(
        actor=user,
        dashboard_type='main',
        request=request,
    )
    
    return DashboardResponse(
        performance_count=dashboard_data['performance_count'],
        business_count=dashboard_data['business_count'],
        alert_count=dashboard_data['alert_count'],
        activity_count=dashboard_data['activity_count'],
        avg_response_time_ms=dashboard_data['avg_response_time_ms'],
    )


@router.get(
    '/platform/overview/',
    response=AnalyticsReportSchema,
    summary="Get platform analytics report",
    description=(
        "Returns the latest analytics report for the platform. "
        "Served from Redis cache (generated daily at 02:30 UTC). "
        "Requires staff or admin access."
    ),
)
async def get_platform_analytics(
    request: HttpRequest,
    days: int = 7,
) -> dict:
    """GET /api/v1/ninja/analytics/platform/overview/?days=7"""
    user = request.auth
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        raise HttpError(403, "Staff access required.")

    cache_key = f"analytics:report:platform:platform:{days}d"
    cached = cache.get(cache_key)

    if cached:
        try:
            return json.loads(cached) if isinstance(cached, str) else cached
        except Exception:
            pass

    # Trigger generation if not cached
    from asgiref.sync import sync_to_async

    @sync_to_async
    def trigger():
        from apps.analytics.tasks.analytics_tasks import run_platform_analytics
        run_platform_analytics.delay(days=days)

    await trigger()

    return {
        "generated_at":    timezone.now().isoformat(),
        "days":            days,
        "scope":           "platform",
        "order_metrics":   {},
        "product_metrics": {},
        "user_metrics":    {},
        "vendor_metrics":  {},
        "anomalies":       [],
        "llm_insights":    "Report generation in progress...",
    }


@router.get(
    '/vendors/{vendor_id}/overview/',
    response=AnalyticsReportSchema,
    summary="Get vendor analytics report",
    description=(
        "Returns the latest analytics report for a specific vendor. "
        "Requires staff, admin, or the vendor themselves."
    ),
)
async def get_vendor_analytics(
    request: HttpRequest,
    vendor_id: int,
    days: int = 7,
) -> dict:
    """GET /api/v1/ninja/analytics/vendors/{vendor_id}/overview/?days=7"""
    user = request.auth
    is_authorized = (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or (getattr(user, "vendor_profile", None) and user.vendor_profile.id == vendor_id)
    )
    if not is_authorized:
        raise HttpError(403, "Vendor access required.")

    cache_key = f"analytics:report:vendor:{vendor_id}:{days}d"
    cached = cache.get(cache_key)

    if cached:
        try:
            return json.loads(cached) if isinstance(cached, str) else cached
        except Exception:
            pass

    from asgiref.sync import sync_to_async

    @sync_to_async
    def trigger():
        from apps.analytics.tasks.analytics_tasks import run_platform_analytics
        run_platform_analytics.delay(days=days, scope="vendor", scope_id=vendor_id)

    await trigger()

    return {
        "generated_at":    timezone.now().isoformat(),
        "days":            days,
        "scope":           "vendor",
        "order_metrics":   {},
        "product_metrics": {},
        "user_metrics":    {},
        "vendor_metrics":  {},
        "anomalies":       [],
        "llm_insights":    "Report generation in progress...",
    }


@router.get('/orders/', response=AnalyticsReportSchema)
async def get_order_analytics(
    request: HttpRequest,
    days: int = 30,
) -> dict:
    """GET /api/v1/ninja/analytics/orders/?days=30"""
    user = request.auth
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        raise HttpError(403, "Staff access required.")

    cache_key = f"analytics:report:orders:platform:{days}d"
    cached = cache.get(cache_key)
    if cached:
        try:
            return json.loads(cached) if isinstance(cached, str) else cached
        except Exception:
            pass

    return {
        "generated_at": timezone.now().isoformat(),
        "days": days,
        "scope": "orders",
        "order_metrics": {},
        "product_metrics": {},
        "user_metrics": {},
        "vendor_metrics": {},
        "anomalies": [],
        "llm_insights": "",
    }


@router.get('/products/', response=AnalyticsReportSchema)
async def get_product_analytics(
    request: HttpRequest,
    days: int = 30,
) -> dict:
    """GET /api/v1/ninja/analytics/products/?days=30"""
    user = request.auth
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        raise HttpError(403, "Staff access required.")

    cache_key = f"analytics:report:products:platform:{days}d"
    cached = cache.get(cache_key)
    if cached:
        try:
            return json.loads(cached) if isinstance(cached, str) else cached
        except Exception:
            pass

    return {
        "generated_at": timezone.now().isoformat(),
        "days": days,
        "scope": "products",
        "order_metrics": {},
        "product_metrics": {},
        "user_metrics": {},
        "vendor_metrics": {},
        "anomalies": [],
        "llm_insights": "",
    }


@router.get('/users/', response=AnalyticsReportSchema)
async def get_user_analytics(
    request: HttpRequest,
    days: int = 30,
) -> dict:
    """GET /api/v1/ninja/analytics/users/?days=30"""
    user = request.auth
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        raise HttpError(403, "Staff access required.")

    cache_key = f"analytics:report:users:platform:{days}d"
    cached = cache.get(cache_key)
    if cached:
        try:
            return json.loads(cached) if isinstance(cached, str) else cached
        except Exception:
            pass

    return {
        "generated_at": timezone.now().isoformat(),
        "days": days,
        "scope": "users",
        "order_metrics": {},
        "product_metrics": {},
        "user_metrics": {},
        "vendor_metrics": {},
        "anomalies": [],
        "llm_insights": "",
    }


@router.get('/realtime/')
async def get_realtime_analytics(request: HttpRequest) -> dict:
    """GET /api/v1/ninja/analytics/realtime/"""
    user = request.auth
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        raise HttpError(403, "Staff access required.")

    cache_key = "analytics:realtime:snapshot"
    cached = cache.get(cache_key)
    if cached:
        try:
            return json.loads(cached) if isinstance(cached, str) else cached
        except Exception:
            pass

    return {
        "generated_at": timezone.now().isoformat(),
        "status": "realtime snapshot not yet generated",
    }


@router.get('/metrics/', response=List[MetricSchema])
async def get_metrics(request: HttpRequest, name: Optional[str] = None, limit: int = 100):
    """
    Get analytics metrics (async).
    Endpoint: GET /api/v1/ninja/analytics/metrics/
    """
    if name:
        metrics = await aget_metrics(name=name, limit=limit)
    else:
        from apps.analytics.models import Metric
        from datetime import timedelta
        since = timezone.now() - timedelta(hours=24)
        metrics = await Metric.aget_recent_metrics(hours=24, limit=limit)
    
    return [
        MetricSchema(
            id=m.id,
            name=m.name,
            metric_type=m.metric_type,
            value=m.value,
            tags=m.tags,
            timestamp=m.timestamp.isoformat(),
        )
        for m in metrics
    ]


@router.get('/performance/', response=List[PerformanceMetricSchema])
async def get_performance_metrics(request: HttpRequest, hours: int = 24, limit: int = 100):
    """
    Get performance metrics (async).
    Endpoint: GET /api/v1/ninja/analytics/performance/
    """
    metrics = await aget_performance_metrics(hours, limit)
    
    return [
        PerformanceMetricSchema(
            id=m.id,
            endpoint=m.endpoint,
            method=m.method,
            response_time_ms=m.response_time_ms,
            status_code=m.status_code,
            timestamp=m.timestamp.isoformat(),
        )
        for m in metrics
    ]


@router.get('/business-metrics/', response=List[BusinessMetricSchema])
async def get_business_metrics(request: HttpRequest, days: int = 30, limit: int = 100):
    """
    Get business metrics (async).
    Endpoint: GET /api/v1/ninja/analytics/business-metrics/
    """
    metrics = await aget_business_metrics(days, limit)
    
    return [
        BusinessMetricSchema(
            id=m.id,
            metric_name=m.metric_name,
            value=m.value,
            period_start=m.period_start.isoformat(),
            period_end=m.period_end.isoformat(),
            created_at=m.created_at.isoformat(),
        )
        for m in metrics
    ]


@router.get('/alerts/', response=List[AlertSchema])
async def get_alerts(request: HttpRequest, status: Optional[str] = None, limit: int = 100):
    """
    Get alerts (async).
    Endpoint: GET /api/v1/ninja/analytics/alerts/
    """
    if status:
        from apps.analytics.models import Alert
        alerts = await Alert.aget_by_status(status, limit)
    else:
        alerts = await aget_alerts(status='firing', limit=limit)
    
    return [
        AlertSchema(
            id=a.id,
            rule_name=a.rule.name,
            status=a.status,
            metric_value=a.metric_value,
            message=a.message,
            fired_at=a.fired_at.isoformat(),
        )
        for a in alerts
    ]


@router.get('/health/', response=HealthCheckResponse)
async def get_analytics_health(request: HttpRequest):
    """
    Get analytics service health check (async).
    Endpoint: GET /api/v1/ninja/analytics/health/
    """
    from apps.analytics.services.health_service import aget_analytics_health

    health = await aget_analytics_health()
    return HealthCheckResponse(**health)


@router.get('/metrics/export/')
def get_analytics_metrics_export(request: HttpRequest):
    """
    Export analytics metrics in Prometheus text format.
    Endpoint: GET /api/v1/ninja/analytics/metrics/export/
    """
    from django.http import HttpResponse
    from apps.analytics.services.metrics_service import get_metrics_service

    metrics_service = get_metrics_service()
    return HttpResponse(
        metrics_service.render_prometheus(),
        content_type="text/plain; version=0.0.4; charset=utf-8",
    )
