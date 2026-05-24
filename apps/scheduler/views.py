"""
Views برای اپ scheduler
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.utils import timezone
from django.db.models import Avg, Count, Q, F
from django.shortcuts import get_object_or_404
from celery.result import AsyncResult
from datetime import timedelta
import logging

from .models import (
    TaskDefinition,
    ScheduledTask,
    TaskExecution,
    TaskLog,
    TaskAlert
)
from .serializers import (
    TaskDefinitionSerializer,
    ScheduledTaskSerializer,
    TaskExecutionSerializer,
    TaskExecutionDetailSerializer,
    TaskLogSerializer,
    TaskAlertSerializer,
    TaskAlertResolveSerializer,
    TaskExecutionCreateSerializer,
    TaskStatisticsSerializer
)
from .tasks import execute_task, run_scheduled_task

logger = logging.getLogger(__name__)


class TaskDefinitionViewSet(viewsets.ModelViewSet):
    """
    ViewSet برای مدیریت تعاریف وظایف
    """
    queryset = TaskDefinition.objects.all()
    serializer_class = TaskDefinitionSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'task_path']
    ordering_fields = ['name', 'task_type', 'created_at']
    ordering = ['name']
    
    def perform_create(self, serializer):
        """ذخیره با کاربر جاری"""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """
        فعال/غیرفعال کردن تعریف وظیفه
        """
        task_def = self.get_object()
        task_def.is_active = not task_def.is_active
        task_def.save()
        
        return Response({
            'status': 'success',
            'is_active': task_def.is_active,
            'message': f"وظیفه {task_def.name} {'فعال' if task_def.is_active else 'غیرفعال'} شد"
        })
    
    @action(detail=True, methods=['get'])
    def executions(self, request, pk=None):
        """
        لیست اجراهای یک تعریف وظیفه
        """
        task_def = self.get_object()
        executions = TaskExecution.objects.filter(
            task_definition=task_def
        ).order_by('-queued_at')[:50]
        
        serializer = TaskExecutionSerializer(executions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """
        اجرای دستی یک وظیفه
        """
        task_def = self.get_object()
        
        if not task_def.is_active:
            return Response({
                'error': 'وظیفه غیرفعال است'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = TaskExecutionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        params = serializer.validated_data.get('params', {})
        priority = serializer.validated_data.get('priority', 5)
        
        # ایجاد رکورد اجرا
        execution = TaskExecution.objects.create(
            task_definition=task_def,
            celery_task_id='pending',
            params=params or task_def.default_params,
            created_by=request.user
        )
        
        # ارسال به Celery
        task = execute_task.apply_async(
            args=[str(execution.id), task_def.task_path],
            kwargs={'params': execution.params},
            queue=task_def.queue_name,
            priority=priority
        )
        
        # بروزرسانی celery_task_id
        execution.celery_task_id = task.id
        execution.save()
        
        return Response({
            'status': 'success',
            'execution_id': str(execution.id),
            'celery_task_id': task.id,
            'message': f"وظیفه {task_def.name} برای اجرا ارسال شد"
        }, status=status.HTTP_201_CREATED)


class ScheduledTaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet برای مدیریت وظایف زمان‌بندی شده
    """
    queryset = ScheduledTask.objects.select_related(
        'task_definition', 'created_by'
    ).all()
    serializer_class = ScheduledTaskSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'task_definition__name']
    ordering_fields = ['name', 'priority', 'next_run_at', 'created_at']
    ordering = ['-priority', 'name']
    
    def get_queryset(self):
        """فیلتر بر اساس query params"""
        queryset = super().get_queryset()
        
        # فیلتر بر اساس وضعیت
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # فیلتر بر اساس نوع زمان‌بندی
        schedule_type = self.request.query_params.get('schedule_type')
        if schedule_type:
            queryset = queryset.filter(schedule_type=schedule_type)
        
        # فیلتر وظایف عقب‌افتاده
        overdue = self.request.query_params.get('overdue')
        if overdue == 'true':
            queryset = queryset.filter(
                status='active',
                next_run_at__lt=timezone.now()
            )
        
        return queryset
    
    def perform_create(self, serializer):
        """ذخیره با کاربر جاری"""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """
        تغییر وضعیت وظیفه زمان‌بندی شده
        """
        scheduled_task = self.get_object()
        
        if scheduled_task.status == 'active':
            scheduled_task.status = 'paused'
        elif scheduled_task.status == 'paused':
            scheduled_task.status = 'active'
        else:
            return Response({
                'error': 'وضعیت فعلی قابل تغییر نیست'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        scheduled_task.save()
        
        return Response({
            'status': 'success',
            'new_status': scheduled_task.status,
            'message': f"وظیفه {scheduled_task.name} {scheduled_task.get_status_display()} شد"
        })
    
    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        """
        اجرای فوری وظیفه زمان‌بندی شده
        """
        scheduled_task = self.get_object()
        
        if scheduled_task.status not in ['active', 'paused']:
            return Response({
                'error': 'وظیفه قابل اجرا نیست'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # اجرای وظیفه
        task = run_scheduled_task.delay(str(scheduled_task.id))
        
        return Response({
            'status': 'success',
            'celery_task_id': task.id,
            'message': f"وظیفه {scheduled_task.name} برای اجرا فوری ارسال شد"
        })
    
    @action(detail=True, methods=['get'])
    def execution_history(self, request, pk=None):
        """
        تاریخچه اجرای وظیفه زمان‌بندی شده
        """
        scheduled_task = self.get_object()
        
        # فیلتر زمانی
        days = int(request.query_params.get('days', 7))
        since = timezone.now() - timedelta(days=days)
        
        executions = TaskExecution.objects.filter(
            scheduled_task=scheduled_task,
            queued_at__gte=since
        ).order_by('-queued_at')
        
        serializer = TaskExecutionSerializer(executions, many=True)
        
        # آمار خلاصه
        stats = executions.aggregate(
            total=Count('id'),
            success=Count('id', filter=Q(status='success')),
            failed=Count('id', filter=Q(status='failed')),
            avg_duration=Avg('duration_seconds', filter=Q(status='success'))
        )
        
        return Response({
            'executions': serializer.data,
            'statistics': stats
        })


class TaskExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet برای مشاهده سوابق اجرا
    """
    queryset = TaskExecution.objects.select_related(
        'task_definition', 'scheduled_task', 'created_by'
    ).all()
    serializer_class = TaskExecutionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['celery_task_id', 'task_definition__name']
    ordering_fields = ['queued_at', 'duration_seconds', 'status']
    ordering = ['-queued_at']
    
    def get_serializer_class(self):
        """انتخاب سریالایزر بر اساس action"""
        if self.action == 'retrieve':
            return TaskExecutionDetailSerializer
        return TaskExecutionSerializer
    
    def get_queryset(self):
        """فیلتر بر اساس query params"""
        queryset = super().get_queryset()
        
        # فیلتر بر اساس وضعیت
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # فیلتر بر اساس task definition
        task_def_id = self.request.query_params.get('task_definition')
        if task_def_id:
            queryset = queryset.filter(task_definition_id=task_def_id)
        
        # فیلتر بر اساس scheduled task
        scheduled_task_id = self.request.query_params.get('scheduled_task')
        if scheduled_task_id:
            queryset = queryset.filter(scheduled_task_id=scheduled_task_id)
        
        # فیلتر زمانی
        days = self.request.query_params.get('days')
        if days:
            since = timezone.now() - timedelta(days=int(days))
            queryset = queryset.filter(queued_at__gte=since)
        
        return queryset
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        بررسی وضعیت اجرای وظیفه از Celery
        """
        execution = self.get_object()
        
        try:
            result = AsyncResult(execution.celery_task_id)
            
            celery_status = {
                'id': result.id,
                'state': result.state,
                'ready': result.ready(),
                'successful': result.successful() if result.ready() else None,
                'failed': result.failed() if result.ready() else None,
                'info': result.info if result.state != 'PENDING' else None
            }
            
            return Response({
                'execution_status': execution.status,
                'celery_status': celery_status
            })
            
        except Exception as e:
            return Response({
                'error': f'خطا در دریافت وضعیت: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        لغو اجرای وظیفه
        """
        execution = self.get_object()
        
        if execution.status not in ['pending', 'running']:
            return Response({
                'error': 'وظیفه قابل لغو نیست'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # لغو در Celery
            result = AsyncResult(execution.celery_task_id)
            result.revoke(terminate=True)
            
            # بروزرسانی وضعیت
            execution.status = 'cancelled'
            execution.completed_at = timezone.now()
            execution.save()
            
            # ثبت لاگ
            TaskLog.objects.create(
                execution=execution,
                level='warning',
                message='وظیفه توسط کاربر لغو شد',
                extra_data={'cancelled_by': request.user.username}
            )
            
            return Response({
                'status': 'success',
                'message': 'وظیفه با موفقیت لغو شد'
            })
            
        except Exception as e:
            return Response({
                'error': f'خطا در لغو وظیفه: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TaskAlertViewSet(viewsets.ModelViewSet):
    """
    ViewSet برای مدیریت هشدارهای وظایف
    """
    queryset = TaskAlert.objects.select_related(
        'task_definition', 'scheduled_task', 'execution', 'resolved_by'
    ).prefetch_related('notified_users').all()
    serializer_class = TaskAlertSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'severity']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """فیلتر بر اساس query params"""
        queryset = super().get_queryset()
        
        # فیلتر هشدارهای حل نشده
        unresolved = self.request.query_params.get('unresolved')
        if unresolved == 'true':
            queryset = queryset.filter(is_resolved=False)
        
        # فیلتر بر اساس شدت
        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)
        
        # فیلتر بر اساس نوع
        alert_type = self.request.query_params.get('alert_type')
        if alert_type:
            queryset = queryset.filter(alert_type=alert_type)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """
        حل کردن هشدار
        """
        alert = self.get_object()
        
        if alert.is_resolved:
            return Response({
                'error': 'هشدار قبلا حل شده است'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = TaskAlertResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.resolution_note = serializer.validated_data['resolution_note']
        alert.save()
        
        return Response({
            'status': 'success',
            'message': 'هشدار با موفقیت حل شد'
        })
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        خلاصه وضعیت هشدارها
        """
        summary = TaskAlert.objects.aggregate(
            total=Count('id'),
            unresolved=Count('id', filter=Q(is_resolved=False)),
            critical=Count('id', filter=Q(severity='critical', is_resolved=False)),
            high=Count('id', filter=Q(severity='high', is_resolved=False)),
            medium=Count('id', filter=Q(severity='medium', is_resolved=False)),
            low=Count('id', filter=Q(severity='low', is_resolved=False))
        )
        
        # هشدارهای اخیر
        recent_alerts = TaskAlert.objects.filter(
            is_resolved=False
        ).order_by('-created_at')[:10]
        
        return Response({
            'summary': summary,
            'recent_alerts': TaskAlertSerializer(recent_alerts, many=True).data
        })


class TaskStatisticsView(viewsets.ViewSet):
    """
    ViewSet برای آمار و گزارشات
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """
        آمار کلی سیستم
        """
        # آمار تعاریف
        definitions_stats = TaskDefinition.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True))
        )
        
        # آمار زمان‌بندی‌ها
        scheduled_stats = ScheduledTask.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='active')),
            paused=Count('id', filter=Q(status='paused')),
            overdue=Count('id', filter=Q(
                status='active',
                next_run_at__lt=timezone.now()
            ))
        )
        
        # آمار اجراها (24 ساعت گذشته)
        since = timezone.now() - timedelta(hours=24)
        executions_stats = TaskExecution.objects.filter(
            queued_at__gte=since
        ).aggregate(
            total=Count('id'),
            running=Count('id', filter=Q(status='running')),
            success=Count('id', filter=Q(status='success')),
            failed=Count('id', filter=Q(status='failed')),
            avg_duration=Avg('duration_seconds', filter=Q(status='success'))
        )
        
        # محاسبه نرخ موفقیت
        total_executions = executions_stats['total'] or 0
        success_executions = executions_stats['success'] or 0
        success_rate = (success_executions / total_executions * 100) if total_executions > 0 else 0
        
        # آمار هشدارها
        alerts_stats = TaskAlert.objects.aggregate(
            unresolved=Count('id', filter=Q(is_resolved=False)),
            critical=Count('id', filter=Q(severity='critical', is_resolved=False))
        )
        
        data = {
            'total_definitions': definitions_stats['total'],
            'active_definitions': definitions_stats['active'],
            'total_scheduled': scheduled_stats['total'],
            'active_scheduled': scheduled_stats['active'],
            'overdue_scheduled': scheduled_stats['overdue'],
            'total_executions': executions_stats['total'],
            'running_executions': executions_stats['running'],
            'success_rate': round(success_rate, 2),
            'average_duration': round(executions_stats['avg_duration'] or 0, 2),
            'unresolved_alerts': alerts_stats['unresolved'],
            'critical_alerts': alerts_stats['critical']
        }
        
        serializer = TaskStatisticsSerializer(data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def performance(self, request):
        """
        آمار عملکرد وظایف
        """
        # فیلتر زمانی
        days = int(request.query_params.get('days', 7))
        since = timezone.now() - timedelta(days=days)
        
        # عملکرد هر task definition
        performance_data = []
        
        for task_def in TaskDefinition.objects.filter(is_active=True):
            stats = TaskExecution.objects.filter(
                task_definition=task_def,
                queued_at__gte=since
            ).aggregate(
                total=Count('id'),
                success=Count('id', filter=Q(status='success')),
                failed=Count('id', filter=Q(status='failed')),
                avg_duration=Avg('duration_seconds', filter=Q(status='success')),
                min_duration=models.Min('duration_seconds', filter=Q(status='success')),
                max_duration=models.Max('duration_seconds', filter=Q(status='success'))
            )
            
            if stats['total'] > 0:
                success_rate = (stats['success'] / stats['total']) * 100
                
                performance_data.append({
                    'task_id': str(task_def.id),
                    'task_name': task_def.name,
                    'total_executions': stats['total'],
                    'success_rate': round(success_rate, 2),
                    'avg_duration': round(stats['avg_duration'] or 0, 2),
                    'min_duration': round(stats['min_duration'] or 0, 2),
                    'max_duration': round(stats['max_duration'] or 0, 2)
                })
        
        # مرتب‌سازی بر اساس تعداد اجرا
        performance_data.sort(key=lambda x: x['total_executions'], reverse=True)
        
        return Response({
            'period_days': days,
            'performance': performance_data
        })