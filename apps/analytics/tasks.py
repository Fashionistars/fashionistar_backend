"""
وظایف Celery برای اپ Analytics
"""
import logging
from datetime import datetime, timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def check_alert_rules():
    """
    بررسی قوانین هشدار و تولید هشدارهای جدید
    """
    try:
        from .services import AnalyticsService
        
        analytics_service = AnalyticsService()
        triggered_alerts = analytics_service.check_alert_rules()
        
        logger.info(f"بررسی قوانین هشدار کامل شد: {len(triggered_alerts)} هشدار تولید شد")
        
        return {
            'status': 'success',
            'triggered_alerts_count': len(triggered_alerts),
            'triggered_alerts': triggered_alerts
        }
        
    except Exception as e:
        logger.error(f"خطا در بررسی قوانین هشدار: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }


@shared_task
def calculate_hourly_metrics():
    """
    محاسبه متریک‌های کسب و کار ساعتی
    """
    try:
        from .services import AnalyticsService
        
        # محاسبه متریک‌ها برای ساعت گذشته
        now = timezone.now()
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)
        
        analytics_service = AnalyticsService()
        metrics = analytics_service.calculate_business_metrics(hour_start, hour_end)
        
        logger.info(f"متریک‌های ساعتی برای {hour_start} - {hour_end} محاسبه شد: {metrics}")
        
        return {
            'status': 'success',
            'period_start': hour_start.isoformat(),
            'period_end': hour_end.isoformat(),
            'metrics': metrics
        }
        
    except Exception as e:
        logger.error(f"خطا در محاسبه متریک‌های ساعتی: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }


@shared_task
def calculate_daily_metrics():
    """
    محاسبه متریک‌های کسب و کار روزانه
    """
    try:
        from .services import AnalyticsService
        from datetime import date
        
        # محاسبه متریک‌ها برای دیروز
        yesterday = date.today() - timedelta(days=1)
        period_start = timezone.make_aware(datetime.combine(yesterday, datetime.min.time()))
        period_end = timezone.make_aware(datetime.combine(yesterday, datetime.max.time()))
        
        analytics_service = AnalyticsService()
        metrics = analytics_service.calculate_business_metrics(period_start, period_end)
        
        logger.info(f"متریک‌های روزانه برای {yesterday} محاسبه شد: {metrics}")
        
        return {
            'status': 'success',
            'date': yesterday.isoformat(),
            'metrics': metrics
        }
        
    except Exception as e:
        logger.error(f"خطا در محاسبه متریک‌های روزانه: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }


@shared_task
def cleanup_old_metrics():
    """
    پاک‌سازی متریک‌های قدیمی
    """
    try:
        from .models import Metric, UserActivity, PerformanceMetric
        
        # پاک‌سازی داده‌های قدیمی‌تر از 30 روز
        cutoff_date = timezone.now() - timedelta(days=30)
        
        # حذف متریک‌های قدیمی
        deleted_metrics = Metric.objects.filter(timestamp__lt=cutoff_date).delete()
        
        # حذف فعالیت‌های قدیمی
        deleted_activities = UserActivity.objects.filter(timestamp__lt=cutoff_date).delete()
        
        # حذف متریک‌های عملکرد قدیمی
        deleted_performance = PerformanceMetric.objects.filter(timestamp__lt=cutoff_date).delete()
        
        logger.info(f"پاک‌سازی داده‌های قدیمی کامل شد. حذف شده: {deleted_metrics[0]} متریک، {deleted_activities[0]} فعالیت، {deleted_performance[0]} متریک عملکرد")
        
        return {
            'status': 'success',
            'cutoff_date': cutoff_date.isoformat(),
            'deleted_metrics': deleted_metrics[0],
            'deleted_activities': deleted_activities[0],
            'deleted_performance_metrics': deleted_performance[0]
        }
        
    except Exception as e:
        logger.error(f"خطا در پاک‌سازی داده‌های قدیمی: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }


@shared_task
def generate_daily_report():
    """
    تولید گزارش روزانه سیستم
    """
    try:
        from .services import AnalyticsService
        from datetime import date
        
        # تولید گزارش برای دیروز
        yesterday = date.today() - timedelta(days=1)
        period_start = timezone.make_aware(datetime.combine(yesterday, datetime.min.time()))
        period_end = timezone.make_aware(datetime.combine(yesterday, datetime.max.time()))
        
        analytics_service = AnalyticsService()
        
        # دریافت متریک‌های کسب و کار
        business_metrics = analytics_service.calculate_business_metrics(period_start, period_end)
        
        # دریافت تحلیل‌های کاربر
        user_analytics = analytics_service.get_user_analytics(days=1)
        
        # دریافت تحلیل‌های عملکرد
        performance_analytics = analytics_service.get_performance_analytics(days=1)
        
        # تدوین گزارش
        report = {
            'date': yesterday.isoformat(),
            'business_metrics': business_metrics,
            'user_analytics': user_analytics,
            'performance_analytics': performance_analytics,
            'generated_at': datetime.now().isoformat()
        }
        
        # در اینجا می‌توانید گزارش را به فایل، ایمیل یا سرویس خارجی ارسال کنید
        logger.info(f"گزارش روزانه برای {yesterday} تولید شد")
        
        return {
            'status': 'success',
            'date': yesterday.isoformat(),
            'report': report
        }
        
    except Exception as e:
        logger.error(f"خطا در تولید گزارش روزانه: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }


@shared_task
def record_performance_metric_async(endpoint, method, response_time_ms, status_code, 
                                   user_id=None, error_message='', metadata=None):
    """
    ثبت متریک عملکرد به صورت async
    """
    try:
        from django.contrib.auth import get_user_model
        from .services import AnalyticsService
        
        User = get_user_model()
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                pass
        
        analytics_service = AnalyticsService()
        analytics_service.record_performance_metric(
            endpoint=endpoint,
            method=method,
            response_time_ms=response_time_ms,
            status_code=status_code,
            user=user,
            error_message=error_message,
            metadata=metadata or {}
        )
        
        return {'status': 'success'}
        
    except Exception as e:
        logger.error(f"خطا در ثبت متریک عملکرد async: {str(e)}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def record_user_activity_async(user_id, action, resource='', resource_id=None,
                              ip_address='', user_agent='', session_id='', metadata=None):
    """
    ثبت فعالیت کاربر به صورت async
    """
    try:
        from django.contrib.auth import get_user_model
        from .models import UserActivity
        
        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(f"کاربر با شناسه {user_id} یافت نشد")
            return {'status': 'error', 'error': 'User not found'}
        
        UserActivity.objects.create(
            user=user,
            action=action,
            resource=resource,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            metadata=metadata or {}
        )
        
        return {'status': 'success'}
        
    except Exception as e:
        logger.error(f"خطا در ثبت فعالیت کاربر async: {str(e)}")
        return {'status': 'error', 'error': str(e)}