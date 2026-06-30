# apps/scheduler/selectors.py
"""
Fashionistar — Scheduler App Selectors.
Provides read-only database query logic and statistics aggregations.
"""

from typing import Dict, Any
from django.db.models import QuerySet, Avg, Count, Q, Min, Max
from django.utils import timezone
from datetime import timedelta

from .models import (
    TaskDefinition,
    ScheduledTask,
    TaskExecution,
    TaskLog,
    TaskAlert
)


def get_task_definitions_queryset() -> QuerySet:
    """Retrieve all active task definitions."""
    return TaskDefinition.objects.all()


def get_scheduled_tasks_queryset() -> QuerySet:
    """Retrieve all scheduled tasks."""
    return ScheduledTask.objects.all()


def get_task_executions_queryset() -> QuerySet:
    """Retrieve all task executions."""
    return TaskExecution.objects.all()


def get_task_logs_queryset() -> QuerySet:
    """Retrieve all task logs."""
    return TaskLog.objects.all()


def get_task_alerts_queryset() -> QuerySet:
    """Retrieve all task alerts."""
    return TaskAlert.objects.all()


def get_scheduler_statistics_overview() -> Dict[str, Any]:
    """
    Calculate system-wide statistics for definitions, schedules, executions, and alerts.
    """
    # Definitions stats
    definitions_stats = TaskDefinition.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True))
    )
    
    # Scheduled tasks stats
    scheduled_stats = ScheduledTask.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active')),
        paused=Count('id', filter=Q(status='paused')),
        overdue=Count('id', filter=Q(
            status='active',
            next_run_at__lt=timezone.now()
        ))
    )
    
    # Executions stats (past 24 hours)
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
    
    # Calculate success rate
    total_executions = executions_stats['total'] or 0
    success_executions = executions_stats['success'] or 0
    success_rate = (success_executions / total_executions * 100) if total_executions > 0 else 0.0
    
    # Alerts stats
    alerts_stats = TaskAlert.objects.aggregate(
        unresolved=Count('id', filter=Q(is_resolved=False)),
        critical=Count('id', filter=Q(severity='critical', is_resolved=False))
    )
    
    return {
        'total_definitions': definitions_stats['total'] or 0,
        'active_definitions': definitions_stats['active'] or 0,
        'total_scheduled': scheduled_stats['total'] or 0,
        'active_scheduled': scheduled_stats['active'] or 0,
        'overdue_scheduled': scheduled_stats['overdue'] or 0,
        'total_executions': executions_stats['total'] or 0,
        'running_executions': executions_stats['running'] or 0,
        'success_rate': round(success_rate, 2),
        'average_duration': round(executions_stats['avg_duration'] or 0.0, 2),
        'unresolved_alerts': alerts_stats['unresolved'] or 0,
        'critical_alerts': alerts_stats['critical'] or 0
    }


def get_scheduler_performance_stats(days: int = 7) -> Dict[str, Any]:
    """
    Calculate run duration and success metrics for active task definitions.
    """
    since = timezone.now() - timedelta(days=days)
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
            min_duration=Min('duration_seconds', filter=Q(status='success')),
            max_duration=Max('duration_seconds', filter=Q(status='success'))
        )
        
        if stats['total'] > 0:
            success_rate = (stats['success'] / stats['total']) * 100
            
            performance_data.append({
                'task_id': str(task_def.id),
                'task_name': task_def.name,
                'total_executions': stats['total'],
                'success_rate': round(success_rate, 2),
                'avg_duration': round(stats['avg_duration'] or 0.0, 2),
                'min_duration': round(stats['min_duration'] or 0.0, 2),
                'max_duration': round(stats['max_duration'] or 0.0, 2)
            })
            
    # Sort by total execution count descending
    performance_data.sort(key=lambda x: x['total_executions'], reverse=True)
    
    return {
        'period_days': days,
        'performance': performance_data
    }
