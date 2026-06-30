# apps/scheduler/apis/sync/scheduler_views.py
"""
DRF sync views for the scheduler app (compatibility and write operations).
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.utils import timezone
from django.db.models import Avg, Count, Q
from celery.result import AsyncResult
from datetime import timedelta
import logging

from ...models import (
    TaskDefinition,
    ScheduledTask,
    TaskExecution,
    TaskLog,
    TaskAlert
)
from ...serializers import (
    TaskDefinitionSerializer,
    ScheduledTaskSerializer,
    TaskExecutionSerializer,
    TaskExecutionDetailSerializer,
    TaskAlertSerializer,
    TaskAlertResolveSerializer,
    TaskExecutionCreateSerializer,
    TaskStatisticsSerializer
)
from ...tasks import execute_task, run_scheduled_task

logger = logging.getLogger(__name__)


class TaskDefinitionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing TaskDefinitions.
    """
    queryset = TaskDefinition.objects.all()
    serializer_class = TaskDefinitionSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'task_path']
    ordering_fields = ['name', 'task_type', 'created_at']
    ordering = ['name']
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle active status of a task definition."""
        task_def = self.get_object()
        task_def.is_active = not task_def.is_active
        task_def.save()
        
        status_str = 'activated' if task_def.is_active else 'deactivated'
        return Response({
            'status': 'success',
            'is_active': task_def.is_active,
            'message': f"Task {task_def.name} {status_str} successfully."
        })
    
    @action(detail=True, methods=['get'])
    def executions(self, request, pk=None):
        """List executions for a task definition."""
        task_def = self.get_object()
        executions = TaskExecution.objects.filter(
            task_definition=task_def
        ).order_by('-queued_at')[:50]
        
        serializer = TaskExecutionSerializer(executions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Manually trigger a task execution."""
        task_def = self.get_object()
        
        if not task_def.is_active:
            return Response({
                'error': 'Task definition is inactive.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = TaskExecutionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        params = serializer.validated_data.get('params', {})
        priority = serializer.validated_data.get('priority', 5)
        
        execution = TaskExecution.objects.create(
            task_definition=task_def,
            celery_task_id='pending',
            params=params or task_def.default_params,
            created_by=request.user
        )
        
        task = execute_task.apply_async(
            args=[str(execution.id), task_def.task_path],
            kwargs={'params': execution.params},
            queue=task_def.queue_name,
            priority=priority
        )
        
        execution.celery_task_id = task.id
        execution.save()
        
        return Response({
            'status': 'success',
            'execution_id': str(execution.id),
            'celery_task_id': task.id,
            'message': f"Task {task_def.name} dispatched for execution."
        }, status=status.HTTP_201_CREATED)


class ScheduledTaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing ScheduledTasks.
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
        queryset = super().get_queryset()
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        schedule_type = self.request.query_params.get('schedule_type')
        if schedule_type:
            queryset = queryset.filter(schedule_type=schedule_type)
        
        overdue = self.request.query_params.get('overdue')
        if overdue == 'true':
            queryset = queryset.filter(
                status='active',
                next_run_at__lt=timezone.now()
            )
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """Toggle active/paused status of a scheduled task."""
        scheduled_task = self.get_object()
        
        if scheduled_task.status == 'active':
            scheduled_task.status = 'paused'
        elif scheduled_task.status == 'paused':
            scheduled_task.status = 'active'
        else:
            return Response({
                'error': 'Current status cannot be toggled.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        scheduled_task.save()
        
        return Response({
            'status': 'success',
            'new_status': scheduled_task.status,
            'message': f"Scheduled task {scheduled_task.name} set to {scheduled_task.get_status_display()}."
        })
    
    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        """Trigger scheduled task run immediately."""
        scheduled_task = self.get_object()
        
        if scheduled_task.status not in ['active', 'paused']:
            return Response({
                'error': 'Scheduled task cannot be run.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        task = run_scheduled_task.delay(str(scheduled_task.id))
        
        return Response({
            'status': 'success',
            'celery_task_id': task.id,
            'message': f"Scheduled task {scheduled_task.name} queued for immediate run."
        })
    
    @action(detail=True, methods=['get'])
    def execution_history(self, request, pk=None):
        """Get history of execution for a scheduled task."""
        scheduled_task = self.get_object()
        
        days = int(request.query_params.get('days', 7))
        since = timezone.now() - timedelta(days=days)
        
        executions = TaskExecution.objects.filter(
            scheduled_task=scheduled_task,
            queued_at__gte=since
        ).order_by('-queued_at')
        
        serializer = TaskExecutionSerializer(executions, many=True)
        
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
    ViewSet for viewing TaskExecutions.
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
        if self.action == 'retrieve':
            return TaskExecutionDetailSerializer
        return TaskExecutionSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        task_def_id = self.request.query_params.get('task_definition')
        if task_def_id:
            queryset = queryset.filter(task_definition_id=task_def_id)
        
        scheduled_task_id = self.request.query_params.get('scheduled_task')
        if scheduled_task_id:
            queryset = queryset.filter(scheduled_task_id=scheduled_task_id)
        
        days = self.request.query_params.get('days')
        if days:
            since = timezone.now() - timedelta(days=int(days))
            queryset = queryset.filter(queued_at__gte=since)
        
        return queryset
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Fetch celery status for execution."""
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
                'error': f'Failed to retrieve status: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel/revoke running task."""
        execution = self.get_object()
        
        if execution.status not in ['pending', 'running']:
            return Response({
                'error': 'Task is not in a cancellable state.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            result = AsyncResult(execution.celery_task_id)
            result.revoke(terminate=True)
            
            execution.status = 'cancelled'
            execution.completed_at = timezone.now()
            execution.save()
            
            TaskLog.objects.create(
                execution=execution,
                level='warning',
                message='Task cancelled by user request.',
                extra_data={'cancelled_by': request.user.username}
            )
            
            return Response({
                'status': 'success',
                'message': 'Task execution cancelled.'
            })
            
        except Exception as e:
            return Response({
                'error': f'Failed to cancel task: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TaskAlertViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing TaskAlerts.
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
        queryset = super().get_queryset()
        
        unresolved = self.request.query_params.get('unresolved')
        if unresolved == 'true':
            queryset = queryset.filter(is_resolved=False)
        
        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)
        
        alert_type = self.request.query_params.get('alert_type')
        if alert_type:
            queryset = queryset.filter(alert_type=alert_type)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark alert as resolved."""
        alert = self.get_object()
        
        if alert.is_resolved:
            return Response({
                'error': 'Alert is already resolved.'
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
            'message': 'Alert resolved successfully.'
        })
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Retrieve count summary of unresolved/critical alerts."""
        summary = TaskAlert.objects.aggregate(
            total=Count('id'),
            unresolved=Count('id', filter=Q(is_resolved=False)),
            critical=Count('id', filter=Q(severity='critical', is_resolved=False)),
            high=Count('id', filter=Q(severity='high', is_resolved=False)),
            medium=Count('id', filter=Q(severity='medium', is_resolved=False)),
            low=Count('id', filter=Q(severity='low', is_resolved=False))
        )
        
        recent_alerts = TaskAlert.objects.filter(
            is_resolved=False
        ).order_by('-created_at')[:10]
        
        return Response({
            'summary': summary,
            'recent_alerts': TaskAlertSerializer(recent_alerts, many=True).data
        })


class TaskStatisticsView(viewsets.ViewSet):
    """
    ViewSet for retrieving statistics.
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Retrieve overall system task definition and schedule statistics."""
        from ...selectors import get_scheduler_statistics_overview
        data = get_scheduler_statistics_overview()
        serializer = TaskStatisticsSerializer(data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def performance(self, request):
        """Retrieve performance stats for active task definitions."""
        from ...selectors import get_scheduler_performance_stats
        days = int(request.query_params.get('days', 7))
        data = get_scheduler_performance_stats(days=days)
        return Response(data)
