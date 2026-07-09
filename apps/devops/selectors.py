# apps/devops/selectors.py
"""
DevOps App Selectors.
Provides read-only database query logic with dual sync/async methods following vendor pattern.
"""
import asyncio
from typing import List, Dict, Any, Optional
from django.db.models import QuerySet
from django.utils import timezone
from datetime import timedelta

from .models import (
    EnvironmentConfig,
    SecretConfig,
    DeploymentHistory,
    HealthCheck,
    ServiceMonitoring
)


# ============================================================================
# Sync Selectors (Thin wrappers for backward compatibility)
# ============================================================================

def get_environment_configs() -> QuerySet:
    """Retrieve all Environment Configs (sync)."""
    return EnvironmentConfig.objects.all()


def get_deployment_histories() -> QuerySet:
    """Retrieve all Deployment Histories (sync)."""
    return DeploymentHistory.objects.all()


def get_health_checks() -> QuerySet:
    """Retrieve all Health Checks (sync)."""
    return HealthCheck.objects.all()


def get_service_monitorings() -> QuerySet:
    """Retrieve all Service Monitoring configurations (sync)."""
    return ServiceMonitoring.objects.all()


def get_recent_deployments(limit: int = 50) -> List[DeploymentHistory]:
    """Get recent deployments (sync)."""
    return list(DeploymentHistory.objects.all().order_by('-started_at')[:limit])


def get_active_environments() -> List[EnvironmentConfig]:
    """Get active environments (sync)."""
    return list(EnvironmentConfig.objects.filter(is_active=True))


def get_recent_health_checks(limit: int = 100) -> List[HealthCheck]:
    """Get recent health checks (sync)."""
    return list(HealthCheck.objects.all().order_by('-checked_at')[:limit])


# ============================================================================
# Async Selectors (Native Django 6.0 async ORM)
# ============================================================================

async def aget_environment_configs() -> List[EnvironmentConfig]:
    """Retrieve all Environment Configs (async)."""
    return await EnvironmentConfig.aget_active_environments()


async def aget_deployment_histories(limit: int = 50) -> List[DeploymentHistory]:
    """Retrieve recent Deployment Histories (async)."""
    return await DeploymentHistory.aget_recent_deployments(limit)


async def aget_health_checks(limit: int = 100) -> List[HealthCheck]:
    """Retrieve recent Health Checks (async)."""
    return await HealthCheck.aget_recent_checks(limit)


async def aget_service_monitorings() -> List[ServiceMonitoring]:
    """Retrieve all active Service Monitoring configurations (async)."""
    return await ServiceMonitoring.aget_active_monitoring()


async def aget_secrets_by_environment(environment_id: str) -> List[SecretConfig]:
    """Get secrets by environment (async)."""
    return await SecretConfig.aget_by_environment(environment_id)


async def aget_devops_dashboard_parallel(environment_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get devops dashboard data in parallel using asyncio.gather.
    This is the primary async dashboard data fetcher.
    """
    tasks = [
        aget_deployment_histories(limit=20),
        aget_health_checks(limit=50),
        aget_service_monitorings(),
    ]
    
    if environment_id:
        tasks.append(aget_secrets_by_environment(environment_id))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    deployments = results[0] if not isinstance(results[0], Exception) else []
    health_checks = results[1] if not isinstance(results[1], Exception) else []
    service_monitorings = results[2] if not isinstance(results[2], Exception) else []
    
    if environment_id:
        secrets = results[3] if not isinstance(results[3], Exception) else []
    else:
        secrets = []
    
    # Calculate aggregates
    successful_deployments = [d for d in deployments if d.status == 'success']
    failed_deployments = [d for d in deployments if d.status == 'failed']
    healthy_checks = [h for h in health_checks if h.status == 'healthy']
    critical_checks = [h for h in health_checks if h.status == 'critical']
    
    return {
        'deployments': deployments,
        'health_checks': health_checks,
        'service_monitorings': service_monitorings,
        'secrets': secrets,
        'deployment_count': len(deployments),
        'successful_deployments': len(successful_deployments),
        'failed_deployments': len(failed_deployments),
        'health_check_count': len(health_checks),
        'healthy_checks': len(healthy_checks),
        'critical_checks': len(critical_checks),
        'monitoring_count': len(service_monitorings),
        'secret_count': len(secrets),
    }

