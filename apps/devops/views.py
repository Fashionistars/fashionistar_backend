# apps/devops/views.py
"""
Legacy wrapper for compatibility with sync imports.
All active code has been migrated to apis/sync/ and apis/async_/.
"""

from .apis.sync.devops_views import (  # noqa: F401
    HealthCheckView,
    EnvironmentHealthView,
    DockerManagementView,
    DockerComposeManagementView,
    DeploymentView,
    RollbackView,
    ServiceUptimeView,
    PerformanceMetricsView,
    EnvironmentConfigViewSet,
    DeploymentHistoryViewSet,
    HealthCheckViewSet,
    ServiceMonitoringViewSet
)