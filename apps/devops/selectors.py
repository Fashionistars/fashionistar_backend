# apps/devops/selectors.py
"""
DevOps App Selectors.
Provides read-only database query logic.
"""
from django.db.models import QuerySet

from .models import (
    EnvironmentConfig,
    DeploymentHistory,
    HealthCheck,
    ServiceMonitoring
)


def get_environment_configs() -> QuerySet:
    """Retrieve all Environment Configs."""
    return EnvironmentConfig.objects.all()


def get_deployment_histories() -> QuerySet:
    """Retrieve all Deployment Histories."""
    return DeploymentHistory.objects.all()


def get_health_checks() -> QuerySet:
    """Retrieve all Health Checks."""
    return HealthCheck.objects.all()


def get_service_monitorings() -> QuerySet:
    """Retrieve all Service Monitoring configurations."""
    return ServiceMonitoring.objects.all()
