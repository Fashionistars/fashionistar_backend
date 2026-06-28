# apps/scheduler/tasks.py
"""
Celery tasks for scheduler app.
Manages and executes scheduled tasks.
"""

from celery import shared_task, Task
from django.utils import timezone
from typing import Dict, Any
import logging
import traceback
import importlib
from datetime import timedelta

from .models import (
    TaskDefinition,
    ScheduledTask,
    TaskExecution,
    TaskLog,
    TaskAlert
)

logger = logging.getLogger(__name__)


class CallbackTask(Task):
    """
    Base class for tasks with callback capability.
    """
    def on_success(self, retval, task_id, args, kwargs):
        """On successful completion."""
        update_task_execution_status(task_id, 'success', result=retval)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """On failure."""
        update_task_execution_status(
            task_id, 
            'failed', 
            error_message=str(exc),
            traceback=str(einfo)
        )
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """On retry."""
        update_task_execution_status(task_id, 'retrying', error_message=str(exc))


@shared_task(bind=True, base=CallbackTask, name='scheduler.execute_task')
def execute_task(self, execution_id: str, task_path: str, params: Dict[str, Any] = None):
    """
    Execute a task based on function path.
    
    Args:
        execution_id: ID of the execution record
        task_path: Full path of the function (module.function)
        params: Input parameters of the function
    
    Returns:
        Result of the function execution
    """
    if params is None:
        params = {}
    
    execution = None
    try:
        # Update status to running
        execution = TaskExecution.objects.get(id=execution_id)
        execution.status = 'running'
        execution.started_at = timezone.now()
        execution.celery_task_id = self.request.id
        execution.worker_name = self.request.hostname
        execution.save()
        
        # Log starting
        TaskLog.objects.create(
            execution=execution,
            level='info',
            message=f'Start executing task: {task_path}',
            extra_data={'params': params}
        )
        
        # Import and execute function
        module_path, function_name = task_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        function = getattr(module, function_name)
        
        # Execute function with parameters
        result = function(**params)
        
        # Update successful status
        execution.status = 'success'
        execution.completed_at = timezone.now()
        execution.result = result if isinstance(result, (dict, list)) else {'result': str(result)}
        execution.calculate_duration()
        execution.save()
        
        # Update stats for scheduled task
        if execution.scheduled_task:
            execution.scheduled_task.success_count += 1
            execution.scheduled_task.total_run_count += 1
            execution.scheduled_task.last_run_at = timezone.now()
            execution.scheduled_task.save()
        
        # Log success
        TaskLog.objects.create(
            execution=execution,
            level='info',
            message='Task executed successfully',
            extra_data={'result': execution.result}
        )
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error in executing task {task_path}: {error_msg}")
        
        if execution:
            # Update error status
            execution.status = 'failed'
            execution.completed_at = timezone.now()
            execution.error_message = error_msg
            execution.traceback = error_traceback
            execution.calculate_duration()
            execution.save()
            
            # Update stats for scheduled task
            if execution.scheduled_task:
                execution.scheduled_task.failure_count += 1
                execution.scheduled_task.total_run_count += 1
                execution.scheduled_task.last_run_at = timezone.now()
                execution.scheduled_task.save()
                
                # Create alert for error
                TaskAlert.objects.create(
                    scheduled_task=execution.scheduled_task,
                    execution=execution,
                    alert_type='failure',
                    severity='high',
                    title=f'Error in executing task {execution.scheduled_task.name}',
                    message=error_msg,
                    details={
                        'task_path': task_path,
                        'params': params,
                        'error': error_msg
                    }
                )
            
            # Log error
            TaskLog.objects.create(
                execution=execution,
                level='error',
                message=f'Error in executing task: {error_msg}',
                extra_data={'traceback': error_traceback}
            )
        
        # Retry if possible
        if execution and execution.retry_count < (execution.scheduled_task.max_retries if execution.scheduled_task else 3):
            execution.retry_count += 1
            execution.save()
            
            retry_delay = execution.scheduled_task.retry_delay if execution.scheduled_task else 60
            raise self.retry(exc=e, countdown=retry_delay)
        
        raise


@shared_task(name='scheduler.run_scheduled_task')
def run_scheduled_task(scheduled_task_id: str):
    """
    Execute a scheduled task.
    
    Args:
        scheduled_task_id: ID of the scheduled task
    """
    try:
        scheduled_task = ScheduledTask.objects.get(id=scheduled_task_id)
        
        # Check status
        if scheduled_task.status != 'active':
            logger.info(f"Task {scheduled_task.name} is inactive")
            return
        
        # Check end time
        if scheduled_task.end_datetime and timezone.now() > scheduled_task.end_datetime:
            scheduled_task.status = 'expired'
            scheduled_task.save()
            logger.info(f"Task {scheduled_task.name} is expired")
            return
        
        # Create execution record
        execution = TaskExecution.objects.create(
            scheduled_task=scheduled_task,
            task_definition=scheduled_task.task_definition,
            celery_task_id='pending',
            params=scheduled_task.params or scheduled_task.task_definition.default_params
        )
        
        # Dispatch task
        task = execute_task.apply_async(
            args=[str(execution.id), scheduled_task.task_definition.task_path],
            kwargs={'params': execution.params},
            queue=scheduled_task.task_definition.queue_name,
            priority=scheduled_task.priority
        )
        
        # Update celery_task_id
        execution.celery_task_id = task.id
        execution.save()
        
        logger.info(f"Task {scheduled_task.name} dispatched for execution: {task.id}")
        
    except ScheduledTask.DoesNotExist:
        logger.error(f"Scheduled task with id {scheduled_task_id} not found")
    except Exception as e:
        logger.error(f"Error in executing scheduled task: {str(e)}")
        raise


@shared_task(name='scheduler.cleanup_old_executions')
def cleanup_old_executions(days: int = 30):
    """
    Cleanup old execution histories.
    
    Args:
        days: Days to retain histories
    
    Returns:
        Number of deleted records
    """
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # Delete old logs
    deleted_logs = TaskLog.objects.filter(
        created_at__lt=cutoff_date
    ).delete()[0]
    
    # Delete old executions
    deleted_executions = TaskExecution.objects.filter(
        queued_at__lt=cutoff_date,
        status__in=['success', 'failed', 'cancelled']
    ).delete()[0]
    
    logger.info(f"Cleanup completed: {deleted_executions} executions and {deleted_logs} logs deleted")
    
    return {
        'deleted_executions': deleted_executions,
        'deleted_logs': deleted_logs
    }


@shared_task(name='scheduler.check_missing_executions')
def check_missing_executions():
    """
    Check scheduled tasks that have not run at their expected times.
    """
    threshold = timezone.now() - timedelta(minutes=5)
    
    # Find tasks that should have run
    missing_tasks = ScheduledTask.objects.filter(
        status='active',
        next_run_at__lt=threshold,
        next_run_at__isnull=False
    )
    
    for task in missing_tasks:
        # Create alert
        TaskAlert.objects.create(
            scheduled_task=task,
            alert_type='missing',
            severity='high',
            title=f'Missed run for task {task.name}',
            message=f'Task {task.name} was not executed at the scheduled time ({task.next_run_at})',
            details={
                'expected_run_at': task.next_run_at.isoformat(),
                'current_time': timezone.now().isoformat()
            }
        )
        
        logger.warning(f"Task {task.name} was not executed at scheduled time")
    
    return {'missing_tasks': missing_tasks.count()}


@shared_task(name='scheduler.monitor_task_performance')
def monitor_task_performance():
    """
    Monitor task performance and generate alert on degradation.
    """
    from django.db.models import Avg, Count
    
    one_day_ago = timezone.now() - timedelta(days=1)
    one_week_ago = timezone.now() - timedelta(days=7)
    
    for task_def in TaskDefinition.objects.filter(is_active=True):
        # Stats for last 24 hours
        recent_stats = TaskExecution.objects.filter(
            task_definition=task_def,
            status='success',
            completed_at__gte=one_day_ago
        ).aggregate(
            avg_duration=Avg('duration_seconds'),
            count=Count('id')
        )
        
        # Stats for last week
        weekly_stats = TaskExecution.objects.filter(
            task_definition=task_def,
            status='success',
            completed_at__gte=one_week_ago,
            completed_at__lt=one_day_ago
        ).aggregate(
            avg_duration=Avg('duration_seconds')
        )
        
        if recent_stats['count'] > 5 and weekly_stats['avg_duration']:
            recent_avg = recent_stats['avg_duration']
            weekly_avg = weekly_stats['avg_duration']
            
            # If recent average is 50% higher than weekly average
            if recent_avg > weekly_avg * 1.5:
                TaskAlert.objects.create(
                    task_definition=task_def,
                    alert_type='performance',
                    severity='medium',
                    title=f'Performance degradation in task {task_def.name}',
                    message=f'Average execution duration increased from {weekly_avg:.2f} to {recent_avg:.2f} seconds',
                    details={
                        'recent_average': recent_avg,
                        'weekly_average': weekly_avg,
                        'increase_percentage': ((recent_avg - weekly_avg) / weekly_avg) * 100
                    }
                )
    
    return {'checked_tasks': TaskDefinition.objects.filter(is_active=True).count()}


def update_task_execution_status(
    task_id: str,
    status: str,
    result: Any = None,
    error_message: str = None,
    traceback: str = None
):
    """
    Update task execution status.
    
    Args:
        task_id: Celery task ID
        status: New status
        result: Result (if success)
        error_message: Error message (if failed)
        traceback: Error traceback details
    """
    try:
        execution = TaskExecution.objects.get(celery_task_id=task_id)
        execution.status = status
        
        if status in ['success', 'failed']:
            execution.completed_at = timezone.now()
            execution.calculate_duration()
        
        if result is not None:
            execution.result = result if isinstance(result, dict) else {'result': str(result)}
        
        if error_message:
            execution.error_message = error_message
        
        if traceback:
            execution.traceback = traceback
        
        execution.save()
        
    except TaskExecution.DoesNotExist:
        logger.warning(f"TaskExecution with celery_task_id={task_id} not found")
    except Exception as e:
        logger.error(f"Error updating task execution status: {str(e)}")


@shared_task(name='scheduler.send_task_alerts')
def send_task_alerts():
    """
    Send unresolved alerts to relevant users.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # Find unresolved alerts that haven't been notified yet
    unnotified_alerts = TaskAlert.objects.filter(
        is_resolved=False,
        notification_sent_at__isnull=True,
        severity__in=['high', 'critical']
    )
    
    for alert in unnotified_alerts:
        try:
            # Find staff users to notify
            admin_users = User.objects.filter(is_staff=True, is_active=True)
            
            # Send notification (integration with notifications app if needed)
            logger.info(f"Sending alert {alert.title} to {admin_users.count()} users")
            
            # Update notification status
            alert.notification_sent_at = timezone.now()
            alert.notified_users.set(admin_users)
            alert.save()
            
        except Exception as e:
            logger.error(f"Error sending alert {alert.id}: {str(e)}")
    
    return {'sent_alerts': unnotified_alerts.count()}