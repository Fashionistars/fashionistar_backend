# apps/devops/apis/async_/devops_views.py
"""
Django-Ninja async views for the DevOps app (reads/GETs).
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from ninja import Router, Schema
from asgiref.sync import sync_to_async

from ...selectors import (
    get_environment_configs,
    get_deployment_histories,
    get_health_checks,
    get_service_monitorings
)
from ...services.health_service import HealthService

router = Router(tags=["devops"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class EnvironmentOut(Schema):
    id: UUID
    name: str
    environment_type: str
    description: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DeploymentOut(Schema):
    id: UUID
    environment_id: UUID
    version: str
    commit_hash: str
    branch: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    artifacts_url: str
    rollback_from_id: Optional[UUID] = None


class HealthCheckOut(Schema):
    id: UUID
    environment_id: UUID
    service_name: str
    endpoint_url: str
    status: str
    response_time: Optional[float] = None
    status_code: Optional[int] = None
    checked_at: datetime


class ServiceMonitoringOut(Schema):
    id: UUID
    environment_id: UUID
    service_name: str
    service_type: str
    health_check_url: str
    check_interval: int
    timeout: int
    is_active: bool
    alert_on_failure: bool
    created_at: datetime
    updated_at: datetime


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/environments/", response=List[EnvironmentOut])
async def list_environments(request):
    """List all registered deployment environments."""
    qs = get_environment_configs()
    return [item async for item in qs]


@router.get("/deployments/", response=List[DeploymentOut])
async def list_deployments(request, environment: Optional[str] = None):
    """List deployment history logs."""
    qs = get_deployment_histories().order_by('-started_at')
    if environment:
        qs = qs.filter(environment__name=environment)
    return [item async for item in qs]


@router.get("/health-checks/", response=List[HealthCheckOut])
async def list_health_checks(request, environment: Optional[str] = None, service: Optional[str] = None, limit: int = 50):
    """Retrieve database log of periodic health check responses."""
    qs = get_health_checks().order_by('-checked_at')
    if environment:
        qs = qs.filter(environment__name=environment)
    if service:
        qs = qs.filter(service_name=service)
    qs = qs[:limit]
    return [item async for item in qs]


@router.get("/services/", response=List[ServiceMonitoringOut])
async def list_services(request, environment: Optional[str] = None):
    """List service nodes configured for automated monitoring."""
    qs = get_service_monitorings()
    if environment:
        qs = qs.filter(environment__name=environment)
    return [item async for item in qs]


@router.get("/uptime/", response=Dict[str, Any])
async def get_service_uptime(request, environment_name: str, service_name: str, hours: int = 24):
    """Fetch uptime statistics for a specific service node."""
    health_service = HealthService(environment_name)
    uptime_data = await sync_to_async(health_service.get_service_uptime)(service_name, hours)
    return uptime_data


@router.get("/performance/", response=Dict[str, Any])
async def get_performance_metrics(request, environment_name: Optional[str] = None, hours: int = 24):
    """Retrieve system resource usage and service speed latency metrics."""
    health_service = HealthService(environment_name)
    metrics = await sync_to_async(health_service.get_performance_metrics)(hours)
    return metrics


@router.get("/system/health/", response=Dict[str, Any])
async def check_system_health(request):
    """Run real-time async comprehensive system health checks."""
    health_service = HealthService()
    result = await sync_to_async(health_service.comprehensive_health_check)()
    return result
