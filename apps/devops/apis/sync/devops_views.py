# apps/devops/apis/sync/devops_views.py
"""
DRF sync views for the DevOps app (compatibility and write operations).
"""
import logging
from rest_framework import status, viewsets, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from apps.common.decorators import with_api_ingress
from ...models import (
    EnvironmentConfig,
    DeploymentHistory,
    HealthCheck,
    ServiceMonitoring
)
from ...services.docker_service import DockerService, DockerComposeService
from ...services.deployment_service import DeploymentService
from ...services.health_service import HealthService
from ...serializers import (
    EnvironmentConfigSerializer,
    DeploymentHistorySerializer,
    HealthCheckSerializer,
    ServiceMonitoringSerializer
)

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """System Health Check endpoint."""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """Execute comprehensive system health check."""
        try:
            health_service = HealthService()
            result = health_service.comprehensive_health_check()
            
            http_status = status.HTTP_200_OK
            if result.get('overall_status') == 'critical':
                http_status = status.HTTP_503_SERVICE_UNAVAILABLE
            
            return Response(result, status=http_status)
            
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e),
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EnvironmentHealthView(APIView):
    """Environment specific health check endpoint."""
    permission_classes = [permissions.IsAuthenticated]
    
    @with_api_ingress(rate='10/m')
    def get(self, request, environment_name):
        """Execute comprehensive health check on a specific environment."""
        try:
            health_service = HealthService(environment_name)
            result = health_service.comprehensive_health_check()
            return Response(result, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Health check error for environment {environment_name}: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class DockerManagementView(APIView):
    """Docker container management and action dispatch."""
    permission_classes = [permissions.IsAuthenticated]
    
    @with_api_ingress(rate='20/m')
    def get(self, request):
        """Fetch running status of all containers."""
        try:
            docker_service = DockerService()
            containers = docker_service.get_all_containers()
            return Response({
                'containers': containers,
                'total_count': len(containers)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching containers: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @with_api_ingress(rate='10/m')
    def post(self, request):
        """Perform life-cycle actions on Docker containers."""
        try:
            action_type = request.data.get('action')
            container_name = request.data.get('container_name')
            
            if not action_type or not container_name:
                return Response({
                    'error': 'action and container_name are required.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            docker_service = DockerService()
            
            if action_type == 'restart':
                success, message = docker_service.restart_container(container_name)
            elif action_type == 'stop':
                success, message = docker_service.stop_container(container_name)
            elif action_type == 'start':
                success, message = docker_service.start_container(container_name)
            else:
                return Response({
                    'error': 'Invalid action type.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            response_status = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
            return Response({
                'success': success,
                'message': message,
                'container_name': container_name,
                'action': action_type
            }, status=response_status)
            
        except Exception as e:
            logger.error(f"Container action error: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DockerComposeManagementView(APIView):
    """Docker Compose service management operations."""
    permission_classes = [permissions.IsAuthenticated]
    
    @with_api_ingress(rate='10/m')
    def get(self, request):
        """Fetch Docker Compose services status."""
        try:
            compose_service = DockerComposeService()
            services_status = compose_service.get_services_status()
            return Response(services_status, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching services status: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @with_api_ingress(rate='5/m')
    def post(self, request):
        """Manage life-cycle of compose stack services."""
        try:
            action_type = request.data.get('action')
            services = request.data.get('services', [])
            
            if not action_type:
                return Response({
                    'error': 'action is required.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            compose_service = DockerComposeService()
            
            if action_type == 'start':
                success, message = compose_service.start_services(services if services else None)
            elif action_type == 'stop':
                success, message = compose_service.stop_services(services if services else None)
            elif action_type == 'restart':
                success, message = compose_service.restart_services(services if services else None)
            elif action_type == 'build':
                no_cache = request.data.get('no_cache', False)
                success, message = compose_service.build_services(services if services else None, no_cache)
            elif action_type == 'pull':
                success, message = compose_service.pull_images(services if services else None)
            else:
                return Response({
                    'error': 'Invalid action type.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            response_status = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
            return Response({
                'success': success,
                'message': message,
                'action': action_type,
                'services': services
            }, status=response_status)
            
        except Exception as e:
            logger.error(f"Compose operation error: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeploymentView(APIView):
    """Trigger application deployments."""
    permission_classes = [permissions.IsAuthenticated]
    
    @with_api_ingress(rate='5/h')
    def post(self, request):
        """Initiate code deployment to environment."""
        try:
            environment_name = request.data.get('environment')
            version = request.data.get('version')
            branch = request.data.get('branch', 'main')
            build_images = request.data.get('build_images', True)
            run_migrations = request.data.get('run_migrations', True)
            restart_services = request.data.get('restart_services', True)
            
            if not environment_name or not version:
                return Response({
                    'error': 'environment and version are required.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            deployment_service = DeploymentService(environment_name)
            deployment = deployment_service.deploy(
                version=version,
                branch=branch,
                user=request.user,
                build_images=build_images,
                run_migrations=run_migrations,
                restart_services=restart_services
            )
            
            serializer = DeploymentHistorySerializer(deployment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except ValueError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Deployment error: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RollbackView(APIView):
    """Trigger deployment rollbacks."""
    permission_classes = [permissions.IsAuthenticated]
    
    @with_api_ingress(rate='3/h')
    def post(self, request):
        """Perform rollback to previous successful deployment."""
        try:
            environment_name = request.data.get('environment')
            target_deployment_id = request.data.get('target_deployment_id')
            
            if not environment_name or not target_deployment_id:
                return Response({
                    'error': 'environment and target_deployment_id are required.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            deployment_service = DeploymentService(environment_name)
            rollback_deployment = deployment_service.rollback(
                target_deployment_id=target_deployment_id,
                user=request.user
            )
            
            serializer = DeploymentHistorySerializer(rollback_deployment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except ValueError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Rollback error: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ServiceUptimeView(APIView):
    """Get service uptime metrics."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, environment_name, service_name):
        """Fetch service uptime report over specified hours."""
        try:
            hours = int(request.GET.get('hours', 24))
            
            health_service = HealthService(environment_name)
            uptime_data = health_service.get_service_uptime(service_name, hours)
            return Response(uptime_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching uptime: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PerformanceMetricsView(APIView):
    """Retrieve system resources and response speed logs."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, environment_name=None):
        """Retrieve aggregated health and system performance metrics."""
        try:
            hours = int(request.GET.get('hours', 24))
            
            health_service = HealthService(environment_name)
            metrics = health_service.get_performance_metrics(hours)
            return Response(metrics, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching performance metrics: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EnvironmentConfigViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Environment configs."""
    queryset = EnvironmentConfig.objects.all()
    serializer_class = EnvironmentConfigSerializer
    permission_classes = [permissions.IsAuthenticated]


class DeploymentHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing application deployments history."""
    queryset = DeploymentHistory.objects.all()
    serializer_class = DeploymentHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        environment = self.request.query_params.get('environment')
        if environment:
            queryset = queryset.filter(environment__name=environment)
        return queryset.order_by('-started_at')


class HealthCheckViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for displaying periodic health check logs."""
    queryset = HealthCheck.objects.all()
    serializer_class = HealthCheckSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        environment = self.request.query_params.get('environment')
        service = self.request.query_params.get('service')
        
        if environment:
            queryset = queryset.filter(environment__name=environment)
        if service:
            queryset = queryset.filter(service_name=service)
            
        return queryset.order_by('-checked_at')


class ServiceMonitoringViewSet(viewsets.ModelViewSet):
    """ViewSet for managing active monitoring config targets."""
    queryset = ServiceMonitoring.objects.all()
    serializer_class = ServiceMonitoringSerializer
    permission_classes = [permissions.IsAuthenticated]
