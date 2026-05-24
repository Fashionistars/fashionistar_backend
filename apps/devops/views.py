"""
ویوهای API برای مدیریت DevOps
"""
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
import json
import logging

from .models import (
    EnvironmentConfig,
    SecretConfig,
    DeploymentHistory,
    HealthCheck,
    ServiceMonitoring
)
from .services.docker_service import DockerService, DockerComposeService
from .services.deployment_service import DeploymentService
from .services.health_service import HealthService
from .serializers import (
    EnvironmentConfigSerializer,
    SecretConfigSerializer,
    DeploymentHistorySerializer,
    HealthCheckSerializer,
    ServiceMonitoringSerializer
)

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """endpoint بررسی سلامت سیستم"""
    
    permission_classes = [permissions.AllowAny]  # برای health check عمومی
    
    def get(self, request):
        """بررسی سلامت کلی سیستم"""
        try:
            health_service = HealthService()
            result = health_service.comprehensive_health_check()
            
            # تعیین HTTP status code بر اساس وضعیت
            http_status = status.HTTP_200_OK
            if result.get('overall_status') == 'critical':
                http_status = status.HTTP_503_SERVICE_UNAVAILABLE
            elif result.get('overall_status') == 'warning':
                http_status = status.HTTP_200_OK  # warning هنوز OK است
            
            return Response(result, status=http_status)
            
        except Exception as e:
            logger.error(f"خطا در health check: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e),
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EnvironmentHealthView(APIView):
    """بررسی سلامت محیط خاص"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    @method_decorator(ratelimit(key='user', rate='10/m', method='GET'))
    def get(self, request, environment_name):
        """بررسی سلامت محیط مشخص"""
        try:
            health_service = HealthService(environment_name)
            result = health_service.comprehensive_health_check()
            
            return Response(result, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"خطا در health check محیط {environment_name}: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class DockerManagementView(APIView):
    """مدیریت Docker containers"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    @method_decorator(ratelimit(key='user', rate='20/m', method='GET'))
    def get(self, request):
        """دریافت وضعیت containers"""
        try:
            docker_service = DockerService()
            containers = docker_service.get_all_containers()
            
            return Response({
                'containers': containers,
                'total_count': len(containers)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"خطا در دریافت وضعیت containers: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @method_decorator(ratelimit(key='user', rate='10/m', method='POST'))
    def post(self, request):
        """عملیات روی containers"""
        try:
            action_type = request.data.get('action')
            container_name = request.data.get('container_name')
            
            if not action_type or not container_name:
                return Response({
                    'error': 'action و container_name الزامی هستند'
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
                    'error': 'عملیات نامعتبر'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            response_status = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
            
            return Response({
                'success': success,
                'message': message,
                'container_name': container_name,
                'action': action_type
            }, status=response_status)
            
        except Exception as e:
            logger.error(f"خطا در عملیات container: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DockerComposeManagementView(APIView):
    """مدیریت Docker Compose services"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    @method_decorator(ratelimit(key='user', rate='10/m', method='GET'))
    def get(self, request):
        """دریافت وضعیت Docker Compose services"""
        try:
            compose_service = DockerComposeService()
            services_status = compose_service.get_services_status()
            
            return Response(services_status, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"خطا در دریافت وضعیت services: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @method_decorator(ratelimit(key='user', rate='5/m', method='POST'))
    def post(self, request):
        """عملیات روی Docker Compose services"""
        try:
            action_type = request.data.get('action')
            services = request.data.get('services', [])
            
            if not action_type:
                return Response({
                    'error': 'action الزامی است'
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
                    'error': 'عملیات نامعتبر'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            response_status = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
            
            return Response({
                'success': success,
                'message': message,
                'action': action_type,
                'services': services
            }, status=response_status)
            
        except Exception as e:
            logger.error(f"خطا در عملیات compose: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeploymentView(APIView):
    """مدیریت deployment"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    @method_decorator(ratelimit(key='user', rate='5/h', method='POST'))
    def post(self, request):
        """شروع deployment جدید"""
        try:
            environment_name = request.data.get('environment')
            version = request.data.get('version')
            branch = request.data.get('branch', 'main')
            build_images = request.data.get('build_images', True)
            run_migrations = request.data.get('run_migrations', True)
            restart_services = request.data.get('restart_services', True)
            
            if not environment_name or not version:
                return Response({
                    'error': 'environment و version الزامی هستند'
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
            logger.error(f"خطا در deployment: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RollbackView(APIView):
    """rollback deployment"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    @method_decorator(ratelimit(key='user', rate='3/h', method='POST'))
    def post(self, request):
        """rollback به deployment قبلی"""
        try:
            environment_name = request.data.get('environment')
            target_deployment_id = request.data.get('target_deployment_id')
            
            if not environment_name or not target_deployment_id:
                return Response({
                    'error': 'environment و target_deployment_id الزامی هستند'
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
            logger.error(f"خطا در rollback: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ServiceUptimeView(APIView):
    """نمایش uptime سرویس‌ها"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, environment_name, service_name):
        """دریافت uptime سرویس مشخص"""
        try:
            hours = int(request.GET.get('hours', 24))
            
            health_service = HealthService(environment_name)
            uptime_data = health_service.get_service_uptime(service_name, hours)
            
            return Response(uptime_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"خطا در دریافت uptime: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PerformanceMetricsView(APIView):
    """متریک‌های عملکرد سیستم"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, environment_name=None):
        """دریافت متریک‌های عملکرد"""
        try:
            hours = int(request.GET.get('hours', 24))
            
            health_service = HealthService(environment_name)
            metrics = health_service.get_performance_metrics(hours)
            
            return Response(metrics, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"خطا در دریافت متریک‌ها: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ViewSets برای مدل‌ها

class EnvironmentConfigViewSet(viewsets.ModelViewSet):
    """ViewSet برای مدیریت محیط‌ها"""
    
    queryset = EnvironmentConfig.objects.all()
    serializer_class = EnvironmentConfigSerializer
    permission_classes = [permissions.IsAuthenticated]


class DeploymentHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet برای نمایش تاریخچه deployment ها"""
    
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
    """ViewSet برای نمایش نتایج health check ها"""
    
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
    """ViewSet برای مدیریت مانیتورینگ سرویس‌ها"""
    
    queryset = ServiceMonitoring.objects.all()
    serializer_class = ServiceMonitoringSerializer
    permission_classes = [permissions.IsAuthenticated]