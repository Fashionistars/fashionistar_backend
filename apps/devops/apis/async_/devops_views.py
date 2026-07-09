# apps/devops/apis/async_/devops_views.py
"""
Django Ninja async views for DevOps domain.
Follows vendor pattern with async endpoints under /api/v1/ninja/devops/.
"""

from ninja import Router
from django.http import HttpRequest
from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from django.utils import timezone

from ...selectors import (
    aget_environment_configs,
    aget_deployment_histories,
    aget_health_checks,
    aget_service_monitorings,
    aget_devops_dashboard_parallel,
)
from ...models import EnvironmentConfig, DeploymentHistory, HealthCheck, ServiceMonitoring
from apps.audit_logs.services.devops.devops_audit import DevOpsAuditService


router = Router(tags=['DevOps'])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class EnvironmentSchema(BaseModel):
    id: UUID
    name: str
    environment_type: str
    description: str
    is_active: bool
    created_at: str
    updated_at: str


class DeploymentSchema(BaseModel):
    id: UUID
    environment_id: UUID
    version: str
    commit_hash: Optional[str]
    branch: str
    status: str
    started_at: str
    completed_at: Optional[str]
    artifacts_url: Optional[str]
    rollback_from_id: Optional[UUID]


class HealthCheckSchema(BaseModel):
    id: UUID
    environment_id: UUID
    service_name: str
    endpoint_url: str
    status: str
    response_time: Optional[float]
    status_code: Optional[int]
    checked_at: str


class ServiceMonitoringSchema(BaseModel):
    id: UUID
    environment_id: UUID
    service_name: str
    service_type: str
    health_check_url: str
    check_interval: int
    timeout: int
    is_active: bool
    alert_on_failure: bool
    created_at: str
    updated_at: str


class DashboardResponse(BaseModel):
    deployment_count: int
    successful_deployments: int
    failed_deployments: int
    health_check_count: int
    healthy_checks: int
    critical_checks: int
    monitoring_count: int
    secret_count: int


class HealthCheckResponse(BaseModel):
    status: str
    database_status: str
    cache_status: str
    environments_count: int
    active_deployments: int
    critical_health_checks: int


# ============================================================================
# Async Endpoints
# ============================================================================

@router.get('/dashboard/', response=DashboardResponse)
async def get_devops_dashboard(request: HttpRequest, environment_id: Optional[str] = None):
    """
    Get devops dashboard data in parallel (async).
    Endpoint: GET /api/v1/ninja/devops/dashboard/
    """
    user = request.auth
    dashboard_data = await aget_devops_dashboard_parallel(environment_id)
    
    # Log audit event
    DevOpsAuditService.log_config_change_applied(
        actor=user,
        config_type='dashboard_view',
        environment_name=environment_id or 'all',
        request=request,
    )
    
    return DashboardResponse(
        deployment_count=dashboard_data['deployment_count'],
        successful_deployments=dashboard_data['successful_deployments'],
        failed_deployments=dashboard_data['failed_deployments'],
        health_check_count=dashboard_data['health_check_count'],
        healthy_checks=dashboard_data['healthy_checks'],
        critical_checks=dashboard_data['critical_checks'],
        monitoring_count=dashboard_data['monitoring_count'],
        secret_count=dashboard_data['secret_count'],
    )


@router.get('/environments/', response=List[EnvironmentSchema])
async def list_environments(request: HttpRequest):
    """
    List all registered deployment environments (async).
    Endpoint: GET /api/v1/ninja/devops/environments/
    """
    environments = await aget_environment_configs()
    
    return [
        EnvironmentSchema(
            id=env.id,
            name=env.name,
            environment_type=env.environment_type,
            description=env.description,
            is_active=env.is_active,
            created_at=env.created_at.isoformat(),
            updated_at=env.updated_at.isoformat(),
        )
        for env in environments
    ]


@router.get('/deployments/', response=List[DeploymentSchema])
async def list_deployments(request: HttpRequest, environment: Optional[str] = None, limit: int = 50):
    """
    List deployment history logs (async).
    Endpoint: GET /api/v1/ninja/devops/deployments/
    """
    if environment:
        from ...models import EnvironmentConfig
        env = await EnvironmentConfig.aget_by_name(environment)
        if env:
            deployments = await DeploymentHistory.aget_by_environment(str(env.id), limit)
        else:
            deployments = []
    else:
        deployments = await DeploymentHistory.aget_recent_deployments(limit)
    
    return [
        DeploymentSchema(
            id=dep.id,
            environment_id=dep.environment_id,
            version=dep.version,
            commit_hash=dep.commit_hash,
            branch=dep.branch,
            status=dep.status,
            started_at=dep.started_at.isoformat(),
            completed_at=dep.completed_at.isoformat() if dep.completed_at else None,
            artifacts_url=dep.artifacts_url,
            rollback_from_id=dep.rollback_from_id,
        )
        for dep in deployments
    ]


@router.get('/health-checks/', response=List[HealthCheckSchema])
async def list_health_checks(request: HttpRequest, environment: Optional[str] = None, service: Optional[str] = None, limit: int = 50):
    """
    Retrieve database log of periodic health check responses (async).
    Endpoint: GET /api/v1/ninja/devops/health-checks/
    """
    if service:
        health_checks = await HealthCheck.aget_by_service(service, limit)
    elif environment:
        from ...models import EnvironmentConfig
        env = await EnvironmentConfig.aget_by_name(environment)
        if env:
            health_checks = await HealthCheck.aget_by_environment(str(env.id), limit)
        else:
            health_checks = []
    else:
        health_checks = await HealthCheck.aget_recent_checks(limit)
    
    return [
        HealthCheckSchema(
            id=check.id,
            environment_id=check.environment_id,
            service_name=check.service_name,
            endpoint_url=check.endpoint_url,
            status=check.status,
            response_time=check.response_time,
            status_code=check.status_code,
            checked_at=check.checked_at.isoformat(),
        )
        for check in health_checks
    ]


@router.get('/services/', response=List[ServiceMonitoringSchema])
async def list_services(request: HttpRequest, environment: Optional[str] = None):
    """
    List service nodes configured for automated monitoring (async).
    Endpoint: GET /api/v1/ninja/devops/services/
    """
    if environment:
        from ...models import EnvironmentConfig
        env = await EnvironmentConfig.aget_by_name(environment)
        if env:
            monitorings = await ServiceMonitoring.aget_by_environment(str(env.id))
        else:
            monitorings = []
    else:
        monitorings = await aget_service_monitorings()
    
    return [
        ServiceMonitoringSchema(
            id=mon.id,
            environment_id=mon.environment_id,
            service_name=mon.service_name,
            service_type=mon.service_type,
            health_check_url=mon.health_check_url,
            check_interval=mon.check_interval,
            timeout=mon.timeout,
            is_active=mon.is_active,
            alert_on_failure=mon.alert_on_failure,
            created_at=mon.created_at.isoformat(),
            updated_at=mon.updated_at.isoformat(),
        )
        for mon in monitorings
    ]


@router.get('/health/', response=HealthCheckResponse)
async def check_system_health(request: HttpRequest):
    """
    Run real-time async comprehensive system health checks (async).
    Endpoint: GET /api/v1/ninja/devops/health/
    """
    from django.core.cache import cache
    from ...models import HealthCheck
    
    # Check database connectivity
    try:
        environments_count = await EnvironmentConfig.objects.acount()
        database_status = "healthy"
    except Exception:
        environments_count = 0
        database_status = "unhealthy"
    
    # Check cache connectivity
    try:
        cache.set('devops_health_check', 'ok', 10)
        cache.get('devops_health_check')
        cache_status = "healthy"
    except Exception:
        cache_status = "unhealthy"
    
    # Get active deployments
    try:
        active_deployments = await DeploymentHistory.objects.filter(status='running').acount()
    except Exception:
        active_deployments = 0
    
    # Get critical health checks
    try:
        critical_health_checks = await HealthCheck.objects.filter(status='critical').acount()
    except Exception:
        critical_health_checks = 0
    
    # Overall status
    overall_status = "healthy" if database_status == "healthy" and cache_status == "healthy" else "degraded"
    
    return HealthCheckResponse(
        status=overall_status,
        database_status=database_status,
        cache_status=cache_status,
        environments_count=environments_count,
        active_deployments=active_deployments,
        critical_health_checks=critical_health_checks,
    )

