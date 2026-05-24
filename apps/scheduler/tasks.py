"""
Celery tasks برای اپ scheduler
مدیریت و اجرای وظایف زمان‌بندی شده
"""
from celery import shared_task, Task
from celery.result import AsyncResult
from django.utils import timezone
from django.db import transaction
from typing import Dict, Any, Optional
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
    کلاس پایه برای تسک‌ها با قابلیت callback
    """
    def on_success(self, retval, task_id, args, kwargs):
        """هنگام اتمام موفق"""
        update_task_execution_status(task_id, 'success', result=retval)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """هنگام خطا"""
        update_task_execution_status(
            task_id, 
            'failed', 
            error_message=str(exc),
            traceback=str(einfo)
        )
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """هنگام تلاش مجدد"""
        update_task_execution_status(task_id, 'retrying', error_message=str(exc))


@shared_task(bind=True, base=CallbackTask, name='scheduler.execute_task')
def execute_task(self, execution_id: str, task_path: str, params: Dict[str, Any] = None):
    """
    اجرای یک وظیفه بر اساس مسیر تابع
    
    Args:
        execution_id: شناسه رکورد اجرا
        task_path: مسیر کامل تابع (module.function)
        params: پارامترهای ورودی تابع
    
    Returns:
        نتیجه اجرای تابع
    """
    if params is None:
        params = {}
    
    execution = None
    try:
        # بروزرسانی وضعیت به در حال اجرا
        execution = TaskExecution.objects.get(id=execution_id)
        execution.status = 'running'
        execution.started_at = timezone.now()
        execution.celery_task_id = self.request.id
        execution.worker_name = self.request.hostname
        execution.save()
        
        # ثبت لاگ شروع
        TaskLog.objects.create(
            execution=execution,
            level='info',
            message=f'شروع اجرای وظیفه: {task_path}',
            extra_data={'params': params}
        )
        
        # import و اجرای تابع
        module_path, function_name = task_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        function = getattr(module, function_name)
        
        # اجرای تابع با پارامترها
        result = function(**params)
        
        # بروزرسانی وضعیت موفق
        execution.status = 'success'
        execution.completed_at = timezone.now()
        execution.result = result if isinstance(result, (dict, list)) else {'result': str(result)}
        execution.calculate_duration()
        execution.save()
        
        # بروزرسانی آمار scheduled task
        if execution.scheduled_task:
            execution.scheduled_task.success_count += 1
            execution.scheduled_task.total_run_count += 1
            execution.scheduled_task.last_run_at = timezone.now()
            execution.scheduled_task.save()
        
        # ثبت لاگ موفقیت
        TaskLog.objects.create(
            execution=execution,
            level='info',
            message='وظیفه با موفقیت اجرا شد',
            extra_data={'result': execution.result}
        )
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"خطا در اجرای وظیفه {task_path}: {error_msg}")
        
        if execution:
            # بروزرسانی وضعیت خطا
            execution.status = 'failed'
            execution.completed_at = timezone.now()
            execution.error_message = error_msg
            execution.traceback = error_traceback
            execution.calculate_duration()
            execution.save()
            
            # بروزرسانی آمار scheduled task
            if execution.scheduled_task:
                execution.scheduled_task.failure_count += 1
                execution.scheduled_task.total_run_count += 1
                execution.scheduled_task.last_run_at = timezone.now()
                execution.scheduled_task.save()
                
                # ایجاد هشدار برای خطا
                TaskAlert.objects.create(
                    scheduled_task=execution.scheduled_task,
                    execution=execution,
                    alert_type='failure',
                    severity='high',
                    title=f'خطا در اجرای وظیفه {execution.scheduled_task.name}',
                    message=error_msg,
                    details={
                        'task_path': task_path,
                        'params': params,
                        'error': error_msg
                    }
                )
            
            # ثبت لاگ خطا
            TaskLog.objects.create(
                execution=execution,
                level='error',
                message=f'خطا در اجرای وظیفه: {error_msg}',
                extra_data={'traceback': error_traceback}
            )
        
        # تلاش مجدد در صورت امکان
        if execution and execution.retry_count < (execution.scheduled_task.max_retries if execution.scheduled_task else 3):
            execution.retry_count += 1
            execution.save()
            
            retry_delay = execution.scheduled_task.retry_delay if execution.scheduled_task else 60
            raise self.retry(exc=e, countdown=retry_delay)
        
        raise


@shared_task(name='scheduler.run_scheduled_task')
def run_scheduled_task(scheduled_task_id: str):
    """
    اجرای یک وظیفه زمان‌بندی شده
    
    Args:
        scheduled_task_id: شناسه وظیفه زمان‌بندی شده
    """
    try:
        scheduled_task = ScheduledTask.objects.get(id=scheduled_task_id)
        
        # بررسی وضعیت
        if scheduled_task.status != 'active':
            logger.info(f"وظیفه {scheduled_task.name} غیرفعال است")
            return
        
        # بررسی زمان پایان
        if scheduled_task.end_datetime and timezone.now() > scheduled_task.end_datetime:
            scheduled_task.status = 'expired'
            scheduled_task.save()
            logger.info(f"وظیفه {scheduled_task.name} منقضی شده است")
            return
        
        # ایجاد رکورد اجرا
        execution = TaskExecution.objects.create(
            scheduled_task=scheduled_task,
            task_definition=scheduled_task.task_definition,
            celery_task_id='pending',
            params=scheduled_task.params or scheduled_task.task_definition.default_params
        )
        
        # اجرای وظیفه
        task = execute_task.apply_async(
            args=[str(execution.id), scheduled_task.task_definition.task_path],
            kwargs={'params': execution.params},
            queue=scheduled_task.task_definition.queue_name,
            priority=scheduled_task.priority
        )
        
        # بروزرسانی celery_task_id
        execution.celery_task_id = task.id
        execution.save()
        
        logger.info(f"وظیفه {scheduled_task.name} برای اجرا ارسال شد: {task.id}")
        
    except ScheduledTask.DoesNotExist:
        logger.error(f"وظیفه زمان‌بندی شده با شناسه {scheduled_task_id} یافت نشد")
    except Exception as e:
        logger.error(f"خطا در اجرای وظیفه زمان‌بندی شده: {str(e)}")
        raise


@shared_task(name='scheduler.cleanup_old_executions')
def cleanup_old_executions(days: int = 30):
    """
    پاکسازی سوابق اجرای قدیمی
    
    Args:
        days: تعداد روزهای نگهداری سوابق
    
    Returns:
        تعداد رکوردهای حذف شده
    """
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # حذف لاگ‌های قدیمی
    deleted_logs = TaskLog.objects.filter(
        created_at__lt=cutoff_date
    ).delete()[0]
    
    # حذف اجراهای قدیمی
    deleted_executions = TaskExecution.objects.filter(
        queued_at__lt=cutoff_date,
        status__in=['success', 'failed', 'cancelled']
    ).delete()[0]
    
    logger.info(f"پاکسازی انجام شد: {deleted_executions} اجرا و {deleted_logs} لاگ حذف شد")
    
    return {
        'deleted_executions': deleted_executions,
        'deleted_logs': deleted_logs
    }


@shared_task(name='scheduler.check_missing_executions')
def check_missing_executions():
    """
    بررسی وظایف زمان‌بندی شده که اجرا نشده‌اند
    """
    threshold = timezone.now() - timedelta(minutes=5)
    
    # یافتن وظایفی که باید اجرا می‌شدند
    missing_tasks = ScheduledTask.objects.filter(
        status='active',
        next_run_at__lt=threshold,
        next_run_at__isnull=False
    )
    
    for task in missing_tasks:
        # ایجاد هشدار
        TaskAlert.objects.create(
            scheduled_task=task,
            alert_type='missing',
            severity='high',
            title=f'عدم اجرای وظیفه {task.name}',
            message=f'وظیفه {task.name} در زمان مقرر ({task.next_run_at}) اجرا نشده است',
            details={
                'expected_run_at': task.next_run_at.isoformat(),
                'current_time': timezone.now().isoformat()
            }
        )
        
        logger.warning(f"وظیفه {task.name} در زمان مقرر اجرا نشده است")
    
    return {'missing_tasks': missing_tasks.count()}


@shared_task(name='scheduler.monitor_task_performance')
def monitor_task_performance():
    """
    پایش عملکرد وظایف و ایجاد هشدار در صورت کاهش کارایی
    """
    # محاسبه میانگین زمان اجرا برای هر task definition
    from django.db.models import Avg, Count
    
    one_day_ago = timezone.now() - timedelta(days=1)
    one_week_ago = timezone.now() - timedelta(days=7)
    
    for task_def in TaskDefinition.objects.filter(is_active=True):
        # آمار روز گذشته
        recent_stats = TaskExecution.objects.filter(
            task_definition=task_def,
            status='success',
            completed_at__gte=one_day_ago
        ).aggregate(
            avg_duration=Avg('duration_seconds'),
            count=Count('id')
        )
        
        # آمار هفته گذشته
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
            
            # اگر میانگین اخیر 50% بیشتر از میانگین هفتگی باشد
            if recent_avg > weekly_avg * 1.5:
                TaskAlert.objects.create(
                    task_definition=task_def,
                    alert_type='performance',
                    severity='medium',
                    title=f'کاهش کارایی در وظیفه {task_def.name}',
                    message=f'میانگین زمان اجرا از {weekly_avg:.2f} به {recent_avg:.2f} ثانیه افزایش یافته است',
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
    بروزرسانی وضعیت اجرای وظیفه
    
    Args:
        task_id: شناسه Celery task
        status: وضعیت جدید
        result: نتیجه (در صورت موفقیت)
        error_message: پیام خطا (در صورت خطا)
        traceback: جزئیات خطا
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
        logger.warning(f"TaskExecution با celery_task_id={task_id} یافت نشد")
    except Exception as e:
        logger.error(f"خطا در بروزرسانی وضعیت task execution: {str(e)}")


@shared_task(name='scheduler.send_task_alerts')
def send_task_alerts():
    """
    ارسال هشدارهای حل نشده به کاربران مربوطه
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # یافتن هشدارهای حل نشده که هنوز اطلاع‌رسانی نشده‌اند
    unnotified_alerts = TaskAlert.objects.filter(
        is_resolved=False,
        notification_sent_at__isnull=True,
        severity__in=['high', 'critical']
    )
    
    for alert in unnotified_alerts:
        try:
            # یافتن کاربران admin
            admin_users = User.objects.filter(is_staff=True, is_active=True)
            
            # ارسال نوتیفیکیشن (این باید با notifications app هماهنگ شود)
            # فعلا فقط لاگ می‌کنیم
            logger.info(f"ارسال هشدار {alert.title} به {admin_users.count()} کاربر")
            
            # بروزرسانی وضعیت اطلاع‌رسانی
            alert.notification_sent_at = timezone.now()
            alert.notified_users.set(admin_users)
            alert.save()
            
        except Exception as e:
            logger.error(f"خطا در ارسال هشدار {alert.id}: {str(e)}")
    
    return {'sent_alerts': unnotified_alerts.count()}