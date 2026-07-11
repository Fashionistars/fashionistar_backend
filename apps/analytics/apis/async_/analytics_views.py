# apps/analytics/apis/async_/analytics_views.py
"""
Django Ninja async views for Analytics domain.
Follows vendor pattern with async endpoints under /api/v1/ninja/analytics/.
"""

import json
from datetime import timedelta
from typing import List, Optional

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError
from pydantic import BaseModel

from apps.analytics.selectors.analytics_selectors import (
    MetricSelector,
    UserActivitySelector,
    PerformanceMetricSelector,
    BusinessMetricSelector,
    AlertSelector,
    aget_alerts,
    aget_analytics_dashboard_parallel,
    aget_business_metrics,
    aget_metrics,
    aget_performance_metrics,
    aget_user_activity,
)
from apps.analytics.services import AnalyticsService
from apps.audit_logs.services.analytics.analytics_audit import AnalyticsAuditService
from apps.common.pagination import async_ninja_paginate
from apps.common.throttling import (
    AnonBurstThrottle,
    UserBurstThrottle,
    UserSustainedThrottle,
    get_ninja_throttle,
)


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
    user_id: Optional[str] = None


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
    rule_id: int
    rule_name: str
    status: str
    severity: str
    metric_value: float
    message: str
    fired_at: str
    resolved_at: Optional[str] = None


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
# PII Redaction Helper
# ============================================================================

def _redact_user_activity(activity) -> dict:
    """Strip PII from user activity before returning to client.

    Never exposes ip_address, user_agent, or session_id in API responses.
    """
    return {
        "id": activity.id,
        "action": activity.action,
        "resource": activity.resource,
        "resource_id": activity.resource_id,
        "timestamp": activity.timestamp.isoformat(),
        "user_id": str(activity.user_id) if activity.user_id else None,
    }


# ============================================================================
# Async Endpoints
# ============================================================================

@router.get(
    '/dashboard/',
    response=DashboardResponse,
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
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


@router.get(
    '/realtime/',
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_realtime_analytics(request: HttpRequest) -> dict:
    """
    Get real-time analytics snapshot (staff only).
    Endpoint: GET /api/v1/ninja/analytics/realtime/

    Returns the latest cached snapshot from Redis. If no snapshot
    is available, returns 202 with a "computing" status and triggers
    async generation via Celery.

    WebSocket: Connect to ws://host/ws/analytics/realtime/ for live updates.
    """
    user = request.auth
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        raise HttpError(403, "Staff access required.")

    cache_key = "analytics:realtime:snapshot"
    cached = cache.get(cache_key)
    if cached:
        try:
            data = json.loads(cached) if isinstance(cached, str) else cached
            data["websocket_url"] = "ws://host/ws/analytics/realtime/"
            return data
        except Exception:
            pass

    # Trigger async generation
    from asgiref.sync import sync_to_async

    @sync_to_async
    def trigger():
        from apps.analytics.tasks.analytics_tasks import run_realtime_analytics
        run_realtime_analytics.delay()

    await trigger()

    return {
        "generated_at": timezone.now().isoformat(),
        "status": "computing",
        "message": "Real-time snapshot is being generated. Try again in a few seconds.",
        "websocket_url": "ws://host/ws/analytics/realtime/",
    }


@router.get(
    '/rollups/',
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_metric_rollups(
    request: HttpRequest,
    metric_name: Optional[str] = None,
    window: str = "1h",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """
    Get pre-aggregated metric rollups for fast dashboard queries (staff only).
    Endpoint: GET /api/v1/ninja/analytics/rollups/?metric_name=order_created&window=1h

    Queries MetricRollup table for pre-computed aggregations.
    Falls back to raw Metric queries if no rollups exist.
    """
    user = request.auth
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        raise HttpError(403, "Staff access required.")

    valid_windows = {"1m", "5m", "1h", "1d"}
    if window not in valid_windows:
        raise HttpError(400, f"Invalid window '{window}'. Allowed: {valid_windows}")

    from apps.analytics.models import MetricRollup
    from datetime import datetime as dt

    dt_from = None
    dt_to = None
    if date_from:
        try:
            dt_from = dt.fromisoformat(date_from)
        except ValueError:
            raise HttpError(400, "Invalid date_from format. Use ISO format.")
    if date_to:
        try:
            dt_to = dt.fromisoformat(date_to)
        except ValueError:
            raise HttpError(400, "Invalid date_to format. Use ISO format.")

    if metric_name:
        rollups = await MetricRollup.aget_rollup(
            name=metric_name,
            window=window,
            date_from=dt_from,
            date_to=dt_to,
            limit=limit,
        )
    else:
        queryset = MetricRollup.objects.filter(window=window)
        if dt_from:
            queryset = queryset.filter(timestamp__gte=dt_from)
        if dt_to:
            queryset = queryset.filter(timestamp__lte=dt_to)
        rollups = [r async for r in queryset.order_by("-timestamp")[:limit]]

    return {
        "window": window,
        "metric_name": metric_name,
        "count": len(rollups),
        "results": [
            {
                "id": r.id,
                "name": r.name,
                "metric_type": r.metric_type,
                "window": r.window,
                "timestamp": r.timestamp.isoformat(),
                "avg": r.avg,
                "min": r.min,
                "max": r.max,
                "count": r.count,
                "sum": r.sum,
            }
            for r in rollups
        ],
    }


@router.get(
    '/metrics/',
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_metrics(
    request: HttpRequest,
    metric_name: Optional[str] = None,
    metric_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    """
    Get analytics metrics (async, paginated).
    Endpoint: GET /api/v1/ninja/analytics/metrics/
    """
    date_from_dt = parse_datetime(date_from) if date_from else None
    date_to_dt = parse_datetime(date_to) if date_to else None

    queryset = MetricSelector.get_queryset(
        metric_name=metric_name,
        metric_type=metric_type,
        date_from=date_from_dt,
        date_to=date_to_dt,
    )
    paginated = await async_ninja_paginate(request, queryset, page=page, page_size=page_size)
    paginated['results'] = [
        MetricSchema(
            id=m.id,
            name=m.name,
            metric_type=m.metric_type,
            value=m.value,
            tags=m.tags,
            timestamp=m.timestamp.isoformat(),
        )
        for m in paginated['results']
    ]
    return paginated


@router.post(
    '/metrics/',
    response=MetricCreatedResponse,
    throttle=get_ninja_throttle(UserBurstThrottle),
)
async def create_metric(request: HttpRequest, payload: CreateMetricRequest):
    """
    Record a new analytics metric.
    Endpoint: POST /api/v1/ninja/analytics/metrics/
    """
    from apps.analytics.models import Metric
    from apps.analytics.services.realtime_service import publish_analytics_event
    from apps.analytics.services.metrics_service import get_metrics_service

    tags = payload.tags or {}
    metric = await Metric.objects.acreate(
        name=payload.name,
        metric_type=payload.metric_type,
        value=payload.value,
        tags=tags,
    )

    get_metrics_service().record_metric_ingested(
        metric_type=payload.metric_type,
        name=payload.name,
    )
    publish_analytics_event(
        event_type="metric_recorded",
        metadata={
            "metric_name": payload.name,
            "metric_type": payload.metric_type,
            "value": payload.value,
            "tags": tags,
        },
    )
    AnalyticsAuditService.log_metric_recorded(
        actor=request.auth,
        metric_name=payload.name,
        metric_type=payload.metric_type,
        value=payload.value,
        request=request,
    )

    return MetricCreatedResponse(
        id=metric.id,
        name=metric.name,
        metric_type=metric.metric_type,
        value=metric.value,
        timestamp=metric.timestamp.isoformat(),
    )


@router.get(
    '/performance/',
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_performance_metrics(
    request: HttpRequest,
    endpoint: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    hours: int = 24,
    page: int = 1,
    page_size: int = 20,
):
    """
    Get performance metrics (async, paginated).
    Endpoint: GET /api/v1/ninja/analytics/performance/
    """
    date_from_dt = parse_datetime(date_from) if date_from else timezone.now() - timedelta(hours=hours)
    date_to_dt = parse_datetime(date_to) if date_to else None

    queryset = PerformanceMetricSelector.get_queryset(
        endpoint=endpoint,
        date_from=date_from_dt,
        date_to=date_to_dt,
    )
    paginated = await async_ninja_paginate(request, queryset, page=page, page_size=page_size)
    paginated['results'] = [
        PerformanceMetricSchema(
            id=m.id,
            endpoint=m.endpoint,
            method=m.method,
            response_time_ms=m.response_time_ms,
            status_code=m.status_code,
            timestamp=m.timestamp.isoformat(),
        )
        for m in paginated['results']
    ]
    return paginated


@router.get(
    '/user-activity/',
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_user_activity(
    request: HttpRequest,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    """
    Get user activity events (async, paginated, PII-redacted).
    Endpoint: GET /api/v1/ninja/analytics/user-activity/

    RBAC: Restricted to staff/admin — contains user activity data.
    """
    user = request.auth
    if not (getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)):
        raise HttpError(403, 'Staff access required.')

    date_from_dt = parse_datetime(date_from) if date_from else None
    date_to_dt = parse_datetime(date_to) if date_to else None

    queryset = UserActivitySelector.get_queryset(
        user_id=user_id,
        action=action,
        date_from=date_from_dt,
        date_to=date_to_dt,
    )
    paginated = await async_ninja_paginate(request, queryset, page=page, page_size=page_size)
    paginated['results'] = [_redact_user_activity(a) for a in paginated['results']]
    return paginated


@router.get(
    '/business-metrics/',
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_business_metrics(
    request: HttpRequest,
    metric_name: Optional[str] = None,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    days: int = 30,
    page: int = 1,
    page_size: int = 20,
):
    """
    Get business metrics (async, paginated).
    Endpoint: GET /api/v1/ninja/analytics/business-metrics/
    """
    period_start_dt = parse_datetime(period_start) if period_start else timezone.now() - timedelta(days=days)
    period_end_dt = parse_datetime(period_end) if period_end else None

    queryset = BusinessMetricSelector.get_queryset(
        metric_name=metric_name,
        period_start=period_start_dt,
        period_end=period_end_dt,
    )
    paginated = await async_ninja_paginate(request, queryset, page=page, page_size=page_size)
    paginated['results'] = [
        BusinessMetricSchema(
            id=m.id,
            metric_name=m.metric_name,
            value=m.value,
            period_start=m.period_start.isoformat(),
            period_end=m.period_end.isoformat(),
            created_at=m.created_at.isoformat(),
        )
        for m in paginated['results']
    ]
    return paginated


@router.post(
    '/business-metrics/',
    response=BusinessMetricCreatedResponse,
    throttle=get_ninja_throttle(UserBurstThrottle),
)
async def create_business_metric(
    request: HttpRequest, payload: CreateBusinessMetricRequest
):
    """
    Record a new business metric.
    Endpoint: POST /api/v1/ninja/analytics/business-metrics/
    """
    from apps.analytics.models import BusinessMetric
    from apps.analytics.services.metrics_service import get_metrics_service

    metric = await BusinessMetric.objects.acreate(
        metric_name=payload.metric_name,
        value=payload.value,
        period_start=parse_datetime(payload.period_start) or timezone.now(),
        period_end=parse_datetime(payload.period_end) or timezone.now(),
    )

    get_metrics_service().record_metric_ingested(
        metric_type="business",
        name=payload.metric_name,
    )
    AnalyticsAuditService.log_business_metric_updated(
        actor=request.auth,
        metric_name=payload.metric_name,
        value=payload.value,
        period=f"{metric.period_start.isoformat()} - {metric.period_end.isoformat()}",
        request=request,
    )

    return BusinessMetricCreatedResponse(
        id=metric.id,
        metric_name=metric.metric_name,
        value=metric.value,
        period_start=metric.period_start.isoformat(),
        period_end=metric.period_end.isoformat(),
        created_at=metric.created_at.isoformat(),
    )


@router.get(
    '/alerts/',
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_alerts(
    request: HttpRequest,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    """
    Get alerts (async, paginated).
    Endpoint: GET /api/v1/ninja/analytics/alerts/
    """
    queryset = AlertSelector.get_queryset(status=status, severity=severity)
    paginated = await async_ninja_paginate(request, queryset, page=page, page_size=page_size)
    paginated['results'] = [
        AlertSchema(
            id=a.id,
            rule_id=a.rule.id,
            rule_name=a.rule.name,
            status=a.status,
            severity=a.rule.severity,
            metric_value=a.metric_value,
            message=a.message,
            fired_at=a.fired_at.isoformat(),
            resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
        )
        for a in paginated['results']
    ]
    return paginated


@router.post(
    '/alerts/{int:alert_id}/resolve/',
    response=AlertResolvedResponse,
    throttle=get_ninja_throttle(UserBurstThrottle),
)
async def resolve_alert(
    request: HttpRequest,
    alert_id: int,
    payload: ResolveAlertRequest,
):
    """
    Resolve a firing analytics alert.
    Endpoint: POST /api/v1/ninja/analytics/alerts/{id}/resolve/
    """
    from apps.analytics.models import Alert

    alert = await sync_to_async(get_object_or_404)(Alert, id=alert_id)
    await alert.aresolve(resolution_notes=payload.resolution_notes)

    AnalyticsAuditService.log_alert_resolved(
        actor=request.auth,
        alert_id=alert.id,
        resolution_notes=payload.resolution_notes or 'Alert resolved',
        request=request,
    )

    return AlertResolvedResponse(
        id=alert.id,
        status=alert.status,
        resolved_at=alert.resolved_at.isoformat(),
        message=alert.message,
    )


@router.get('/health/', response=HealthCheckResponse, auth=None)
async def get_analytics_health(request: HttpRequest):
    """
    Get analytics service health check (async).
    Endpoint: GET /api/v1/ninja/analytics/health/
    """
    from apps.analytics.services.health_service import aget_analytics_health

    health = await aget_analytics_health()
    return HealthCheckResponse(**health)


@router.get('/metrics/export/', auth=None)
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
