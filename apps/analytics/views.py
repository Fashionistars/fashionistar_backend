"""
Views برای API های Analytics
"""
import logging
from datetime import datetime, timedelta
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Q

from .models import Metric, UserActivity, PerformanceMetric, BusinessMetric, AlertRule, Alert
from .serializers import (
    MetricSerializer, UserActivitySerializer, PerformanceMetricSerializer,
    BusinessMetricSerializer, AlertRuleSerializer, AlertSerializer,
    RecordMetricSerializer, UserAnalyticsQuerySerializer,
    PerformanceAnalyticsQuerySerializer, BusinessMetricsQuerySerializer
)
from .services import AnalyticsService

logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    """
    صفحه‌بندی استاندارد برای نتایج
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 1000


class MetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet برای مشاهده متریک‌ها
    """
    queryset = Metric.objects.all()
    serializer_class = MetricSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """
        فیلتر کردن متریک‌ها بر اساس پارامترهای جستجو
        """
        queryset = super().get_queryset()
        
        # فیلتر بر اساس نام
        name = self.request.query_params.get('name')
        if name:
            queryset = queryset.filter(name__icontains=name)
        
        # فیلتر بر اساس نوع
        metric_type = self.request.query_params.get('metric_type')
        if metric_type:
            queryset = queryset.filter(metric_type=metric_type)
        
        # فیلتر بر اساس محدوده زمانی
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            try:
                start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                queryset = queryset.filter(timestamp__gte=start_date)
            except ValueError:
                pass
        
        if end_date:
            try:
                end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                queryset = queryset.filter(timestamp__lte=end_date)
            except ValueError:
                pass
        
        return queryset.order_by('-timestamp')


class UserActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet برای مشاهده فعالیت‌های کاربران
    """
    queryset = UserActivity.objects.all()
    serializer_class = UserActivitySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """
        فیلتر کردن فعالیت‌ها بر اساس پارامترهای جستجو
        """
        queryset = super().get_queryset()
        
        # فیلتر بر اساس کاربر
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # فیلتر بر اساس عمل
        action = self.request.query_params.get('action')
        if action:
            queryset = queryset.filter(action__icontains=action)
        
        # فیلتر بر اساس منبع
        resource = self.request.query_params.get('resource')
        if resource:
            queryset = queryset.filter(resource__icontains=resource)
        
        return queryset.order_by('-timestamp')


class PerformanceMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet برای مشاهده متریک‌های عملکرد
    """
    queryset = PerformanceMetric.objects.all()
    serializer_class = PerformanceMetricSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """
        فیلتر کردن متریک‌های عملکرد بر اساس پارامترهای جستجو
        """
        queryset = super().get_queryset()
        
        # فیلتر بر اساس endpoint
        endpoint = self.request.query_params.get('endpoint')
        if endpoint:
            queryset = queryset.filter(endpoint__icontains=endpoint)
        
        # فیلتر بر اساس متد
        method = self.request.query_params.get('method')
        if method:
            queryset = queryset.filter(method=method)
        
        # فیلتر بر اساس کد وضعیت
        status_code = self.request.query_params.get('status_code')
        if status_code:
            queryset = queryset.filter(status_code=status_code)
        
        # فیلتر خطاها
        errors_only = self.request.query_params.get('errors_only')
        if errors_only and errors_only.lower() == 'true':
            queryset = queryset.filter(status_code__gte=400)
        
        return queryset.order_by('-timestamp')


class BusinessMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet برای مشاهده متریک‌های کسب و کار
    """
    queryset = BusinessMetric.objects.all()
    serializer_class = BusinessMetricSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination


class AlertRuleViewSet(viewsets.ModelViewSet):
    """
    ViewSet برای مدیریت قوانین هشدار
    """
    queryset = AlertRule.objects.all()
    serializer_class = AlertRuleSerializer
    permission_classes = [IsAdminUser]


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet برای مشاهده هشدارها
    """
    queryset = Alert.objects.all()
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """
        فیلتر کردن هشدارها بر اساس پارامترهای جستجو
        """
        queryset = super().get_queryset()
        
        # فیلتر بر اساس وضعیت
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # فیلتر بر اساس سطح اهمیت
        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(rule__severity=severity)
        
        return queryset.order_by('-fired_at')
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def resolve_all(self, request):
        """
        حل تمام هشدارهای فعال
        """
        try:
            updated_count = Alert.objects.filter(status='firing').update(
                status='resolved',
                resolved_at=timezone.now()
            )
            
            return Response({
                'message': f'{updated_count} هشدار حل شد',
                'resolved_count': updated_count
            })
        except Exception as e:
            logger.error(f"خطا در حل هشدارها: {str(e)}")
            return Response(
                {'error': 'خطا در حل هشدارها'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_metric(request):
    """
    ثبت متریک جدید
    """
    serializer = RecordMetricSerializer(data=request.data)
    if serializer.is_valid():
        try:
            analytics_service = AnalyticsService()
            metric = analytics_service.record_metric(
                name=serializer.validated_data['name'],
                value=serializer.validated_data['value'],
                metric_type=serializer.validated_data['metric_type'],
                tags=serializer.validated_data.get('tags', {})
            )
            
            response_serializer = MetricSerializer(metric)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"خطا در ثبت متریک: {str(e)}")
            return Response(
                {'error': 'خطا در ثبت متریک'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_analytics(request):
    """
    دریافت تحلیل‌های کاربر
    """
    serializer = UserAnalyticsQuerySerializer(data=request.GET)
    if serializer.is_valid():
        try:
            analytics_service = AnalyticsService()
            analytics_data = analytics_service.get_user_analytics(
                user_id=serializer.validated_data.get('user_id'),
                days=serializer.validated_data['days']
            )
            
            return Response(analytics_data)
        
        except Exception as e:
            logger.error(f"خطا در دریافت تحلیل‌های کاربر: {str(e)}")
            return Response(
                {'error': 'خطا در دریافت تحلیل‌های کاربر'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def performance_analytics(request):
    """
    دریافت تحلیل‌های عملکرد
    """
    serializer = PerformanceAnalyticsQuerySerializer(data=request.GET)
    if serializer.is_valid():
        try:
            analytics_service = AnalyticsService()
            analytics_data = analytics_service.get_performance_analytics(
                days=serializer.validated_data['days']
            )
            
            return Response(analytics_data)
        
        except Exception as e:
            logger.error(f"خطا در دریافت تحلیل‌های عملکرد: {str(e)}")
            return Response(
                {'error': 'خطا در دریافت تحلیل‌های عملکرد'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def calculate_business_metrics(request):
    """
    محاسبه متریک‌های کسب و کار
    """
    serializer = BusinessMetricsQuerySerializer(data=request.data)
    if serializer.is_valid():
        try:
            analytics_service = AnalyticsService()
            metrics = analytics_service.calculate_business_metrics(
                period_start=serializer.validated_data['period_start'],
                period_end=serializer.validated_data['period_end']
            )
            
            return Response({
                'message': 'متریک‌های کسب و کار محاسبه شد',
                'metrics': metrics
            })
        
        except Exception as e:
            logger.error(f"خطا در محاسبه متریک‌های کسب و کار: {str(e)}")
            return Response(
                {'error': 'خطا در محاسبه متریک‌های کسب و کار'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def system_overview(request):
    """
    دریافت بررسی کلی سیستم
    """
    try:
        analytics_service = AnalyticsService()
        overview = analytics_service.get_system_overview()
        
        return Response(overview)
    
    except Exception as e:
        logger.error(f"خطا در دریافت بررسی کلی سیستم: {str(e)}")
        return Response(
            {'error': 'خطا در دریافت بررسی کلی سیستم'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAdminUser])
def check_alerts(request):
    """
    بررسی قوانین هشدار
    """
    try:
        analytics_service = AnalyticsService()
        triggered_alerts = analytics_service.check_alert_rules()
        
        return Response({
            'message': f'{len(triggered_alerts)} هشدار تولید شد',
            'triggered_alerts': triggered_alerts
        })
    
    except Exception as e:
        logger.error(f"خطا در بررسی هشدارها: {str(e)}")
        return Response(
            {'error': 'خطا در بررسی هشدارها'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )