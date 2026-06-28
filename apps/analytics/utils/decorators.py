"""
Decorators برای ردیابی خودکار متریک‌ها
"""
import time
import functools
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def track_performance(metric_name=None):
    """
    Decorator برای ردیابی زمان اجرای توابع
    
    Args:
        metric_name: نام دلخواه برای متریک (اختیاری)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # بررسی اینکه آیا analytics فعال است
            if not getattr(settings, 'ANALYTICS_ENABLED', True):
                return func(*args, **kwargs)
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                
                # محاسبه زمان اجرا
                execution_time = (time.time() - start_time) * 1000  # میلی‌ثانیه
                
                # ثبت متریک
                try:
                    from ..services import AnalyticsService
                    
                    analytics_service = AnalyticsService()
                    name = metric_name or f"function.{func.__module__}.{func.__name__}.execution_time"
                    
                    analytics_service.record_metric(
                        name=name,
                        value=execution_time,
                        metric_type='timer',
                        tags={
                            'function': func.__name__,
                            'module': func.__module__,
                            'success': True
                        }
                    )
                except Exception as e:
                    logger.error(f"خطا در ثبت متریک عملکرد: {str(e)}")
                
                return result
                
            except Exception as e:
                # ثبت متریک خطا
                execution_time = (time.time() - start_time) * 1000
                
                try:
                    from ..services import AnalyticsService
                    
                    analytics_service = AnalyticsService()
                    name = metric_name or f"function.{func.__module__}.{func.__name__}.execution_time"
                    
                    analytics_service.record_metric(
                        name=name,
                        value=execution_time,
                        metric_type='timer',
                        tags={
                            'function': func.__name__,
                            'module': func.__module__,
                            'success': False,
                            'error': str(e)
                        }
                    )
                except Exception as metric_error:
                    logger.error(f"خطا در ثبت متریک خطا: {str(metric_error)}")
                
                raise e
        
        return wrapper
    return decorator


def track_calls(metric_name=None):
    """
    Decorator برای شمارش تعداد فراخوانی توابع
    
    Args:
        metric_name: نام دلخواه برای متریک (اختیاری)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # بررسی اینکه آیا analytics فعال است
            if not getattr(settings, 'ANALYTICS_ENABLED', True):
                return func(*args, **kwargs)
            
            try:
                result = func(*args, **kwargs)
                
                # ثبت متریک شمارش
                try:
                    from ..services import AnalyticsService
                    
                    analytics_service = AnalyticsService()
                    name = metric_name or f"function.{func.__module__}.{func.__name__}.calls"
                    
                    analytics_service.record_metric(
                        name=name,
                        value=1,
                        metric_type='counter',
                        tags={
                            'function': func.__name__,
                            'module': func.__module__,
                            'success': True
                        }
                    )
                except Exception as e:
                    logger.error(f"خطا در ثبت متریک شمارش: {str(e)}")
                
                return result
                
            except Exception as e:
                # ثبت متریک خطا
                try:
                    from ..services import AnalyticsService
                    
                    analytics_service = AnalyticsService()
                    name = metric_name or f"function.{func.__module__}.{func.__name__}.errors"
                    
                    analytics_service.record_metric(
                        name=name,
                        value=1,
                        metric_type='counter',
                        tags={
                            'function': func.__name__,
                            'module': func.__module__,
                            'error': str(e)
                        }
                    )
                except Exception as metric_error:
                    logger.error(f"خطا در ثبت متریک خطا: {str(metric_error)}")
                
                raise e
        
        return wrapper
    return decorator


def track_user_action(action_name, resource_name=None):
    """
    Decorator برای ردیابی اعمال کاربران
    
    Args:
        action_name: نام عمل
        resource_name: نام منبع (اختیاری)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # بررسی اینکه آیا analytics فعال است
            if not getattr(settings, 'ANALYTICS_ENABLED', True):
                return func(*args, **kwargs)
            
            # تلاش برای یافتن کاربر از args
            user = None
            request = None
            
            # جستجوی کاربر در args
            for arg in args:
                if hasattr(arg, 'user') and hasattr(arg.user, 'is_authenticated'):
                    if arg.user.is_authenticated:
                        user = arg.user
                        request = arg
                        break
                elif hasattr(arg, 'is_authenticated') and arg.is_authenticated:
                    user = arg
                    break
            
            try:
                result = func(*args, **kwargs)
                
                # ثبت فعالیت کاربر
                if user:
                    try:
                        from ..services import AnalyticsService
                        
                        analytics_service = AnalyticsService()
                        resource = resource_name or func.__name__
                        
                        analytics_service.record_user_activity(
                            user=user,
                            action=action_name,
                            resource=resource,
                            metadata={
                                'function': func.__name__,
                                'module': func.__module__,
                                'success': True
                            },
                            request=request
                        )
                    except Exception as e:
                        logger.error(f"خطا در ثبت فعالیت کاربر: {str(e)}")
                
                return result
                
            except Exception as e:
                # ثبت فعالیت خطا
                if user:
                    try:
                        from ..services import AnalyticsService
                        
                        analytics_service = AnalyticsService()
                        resource = resource_name or func.__name__
                        
                        analytics_service.record_user_activity(
                            user=user,
                            action=f"{action_name}_error",
                            resource=resource,
                            metadata={
                                'function': func.__name__,
                                'module': func.__module__,
                                'success': False,
                                'error': str(e)
                            },
                            request=request
                        )
                    except Exception as metric_error:
                        logger.error(f"خطا در ثبت فعالیت خطا: {str(metric_error)}")
                
                raise e
        
        return wrapper
    return decorator