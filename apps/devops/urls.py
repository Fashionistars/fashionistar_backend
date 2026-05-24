"""
URL patterns برای اپلیکیشن DevOps
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router برای ViewSets
router = DefaultRouter()
router.register(r'environments', views.EnvironmentConfigViewSet, basename='environment')
router.register(r'deployments', views.DeploymentHistoryViewSet, basename='deployment')
router.register(r'health-checks', views.HealthCheckViewSet, basename='healthcheck')
router.register(r'service-monitoring', views.ServiceMonitoringViewSet, basename='servicemonitoring')

app_name = 'devops'

urlpatterns = [
    # Health Check endpoints
    path('health/', views.HealthCheckView.as_view(), name='health_check'),
    path('health/<str:environment_name>/', views.EnvironmentHealthView.as_view(), name='environment_health'),
    
    # Docker Management
    path('docker/containers/', views.DockerManagementView.as_view(), name='docker_containers'),
    path('docker/compose/', views.DockerComposeManagementView.as_view(), name='docker_compose'),
    
    # Deployment Management
    path('deploy/', views.DeploymentView.as_view(), name='deploy'),
    path('rollback/', views.RollbackView.as_view(), name='rollback'),
    
    # Monitoring & Metrics
    path('uptime/<str:environment_name>/<str:service_name>/', 
         views.ServiceUptimeView.as_view(), name='service_uptime'),
    path('metrics/', views.PerformanceMetricsView.as_view(), name='performance_metrics'),
    path('metrics/<str:environment_name>/', 
         views.PerformanceMetricsView.as_view(), name='environment_metrics'),
    
    # ViewSets routes
    path('api/', include(router.urls)),
]