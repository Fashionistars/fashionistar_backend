"""
Analytics API Views for Fashionistar.
"""

import logging
from datetime import datetime
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone

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
    Standard pagination for analytics results.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 1000


class MetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing system telemetry metrics.
    """
    queryset = Metric.objects.all()
    serializer_class = MetricSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        name = self.request.query_params.get('name')
        if name:
            queryset = queryset.filter(name__icontains=name)
        
        metric_type = self.request.query_params.get('metric_type')
        if metric_type:
            queryset = queryset.filter(metric_type=metric_type)
        
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
    ViewSet for auditing user activities.
    """
    queryset = UserActivity.objects.all()
    serializer_class = UserActivitySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        action_param = self.request.query_params.get('action')
        if action_param:
            queryset = queryset.filter(action__icontains=action_param)
        
        resource = self.request.query_params.get('resource')
        if resource:
            queryset = queryset.filter(resource__icontains=resource)
        
        return queryset.order_by('-timestamp')


class PerformanceMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for checking API latencies.
    """
    queryset = PerformanceMetric.objects.all()
    serializer_class = PerformanceMetricSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        endpoint = self.request.query_params.get('endpoint')
        if endpoint:
            queryset = queryset.filter(endpoint__icontains=endpoint)
        
        method = self.request.query_params.get('method')
        if method:
            queryset = queryset.filter(method=method)
        
        status_code = self.request.query_params.get('status_code')
        if status_code:
            queryset = queryset.filter(status_code=status_code)
        
        errors_only = self.request.query_params.get('errors_only')
        if errors_only and errors_only.lower() == 'true':
            queryset = queryset.filter(status_code__gte=400)
        
        return queryset.order_by('-timestamp')


class BusinessMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing business aggregates (admin only).
    """
    queryset = BusinessMetric.objects.all()
    serializer_class = BusinessMetricSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination


class AlertRuleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing alert rules (admin only).
    """
    queryset = AlertRule.objects.all()
    serializer_class = AlertRuleSerializer
    permission_classes = [IsAdminUser]


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing fired alerts.
    """
    queryset = Alert.objects.all()
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(rule__severity=severity)
        
        return queryset.order_by('-fired_at')
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def resolve_all(self, request):
        """
        Resolve all currently firing alerts.
        """
        try:
            updated_count = Alert.objects.filter(status='firing').update(
                status='resolved',
                resolved_at=timezone.now()
            )
            
            return Response({
                'message': f'{updated_count} alerts resolved successfully.',
                'resolved_count': updated_count
            })
        except Exception as e:
            logger.error(f"Error resolving alerts: {str(e)}")
            return Response(
                {'error': 'Failed to resolve alerts.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_metric(request):
    """
    Record a new telemetry metric.
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
            logger.error(f"Error recording metric: {str(e)}")
            return Response(
                {'error': 'Failed to record metric.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_analytics(request):
    """
    Retrieve user activity statistics.
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
            logger.error(f"Error getting user analytics: {str(e)}")
            return Response(
                {'error': 'Failed to retrieve user analytics.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def performance_analytics(request):
    """
    Retrieve API latency analytics.
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
            logger.error(f"Error getting performance analytics: {str(e)}")
            return Response(
                {'error': 'Failed to retrieve performance analytics.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def calculate_business_metrics(request):
    """
    Calculate e-commerce aggregates.
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
                'message': 'Business metrics calculated successfully.',
                'metrics': metrics
            })
        
        except Exception as e:
            logger.error(f"Error calculating business metrics: {str(e)}")
            return Response(
                {'error': 'Failed to calculate business metrics.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def system_overview(request):
    """
    Retrieve a system-wide overview of active indicators.
    """
    try:
        analytics_service = AnalyticsService()
        overview = analytics_service.get_system_overview()
        
        return Response(overview)
    
    except Exception as e:
        logger.error(f"Error getting system overview: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve system overview.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAdminUser])
def check_alerts(request):
    """
    Evaluate alert rules.
    """
    try:
        analytics_service = AnalyticsService()
        triggered_alerts = analytics_service.check_alert_rules()
        
        return Response({
            'message': f'{len(triggered_alerts)} alerts evaluated/triggered.',
            'triggered_alerts': triggered_alerts
        })
    
    except Exception as e:
        logger.error(f"Error evaluating alerts: {str(e)}")
        return Response(
            {'error': 'Failed to evaluate alert rules.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )