"""
تنظیمات مربوط به اپ Analytics
"""
from django.conf import settings

# تنظیمات پیش‌فرض Analytics
ANALYTICS_SETTINGS = {
    # فعال/غیرفعال کردن Analytics
    'ENABLED': getattr(settings, 'ANALYTICS_ENABLED', True),
    
    # تنظیمات ردیابی عملکرد
    'PERFORMANCE_TRACKING': {
        'ENABLED': getattr(settings, 'ANALYTICS_PERFORMANCE_TRACKING_ENABLED', True),
        'EXCLUDE_PATHS': getattr(settings, 'ANALYTICS_PERFORMANCE_EXCLUDE_PATHS', [
            '/admin/',
            '/static/',
            '/media/',
            '/health/',
            '/metrics/',
        ]),
        'EXCLUDE_METHODS': getattr(settings, 'ANALYTICS_PERFORMANCE_EXCLUDE_METHODS', ['OPTIONS']),
        'TRACK_ANONYMOUS_USERS': getattr(settings, 'ANALYTICS_TRACK_ANONYMOUS_USERS', True),
    },
    
    # تنظیمات ردیابی فعالیت کاربران
    'USER_ACTIVITY_TRACKING': {
        'ENABLED': getattr(settings, 'ANALYTICS_USER_ACTIVITY_TRACKING_ENABLED', True),
        'EXCLUDE_PATHS': getattr(settings, 'ANALYTICS_USER_ACTIVITY_EXCLUDE_PATHS', [
            '/admin/',
            '/static/',
            '/media/',
            '/health/',
        ]),
        'TRACK_GET_REQUESTS': getattr(settings, 'ANALYTICS_TRACK_GET_REQUESTS', False),
        'TRACK_ANONYMOUS_USERS': getattr(settings, 'ANALYTICS_TRACK_ANONYMOUS_USERS', False),
    },
    
    # تنظیمات هشدارها
    'ALERTS': {
        'ENABLED': getattr(settings, 'ANALYTICS_ALERTS_ENABLED', True),
        'CHECK_INTERVAL_MINUTES': getattr(settings, 'ANALYTICS_ALERT_CHECK_INTERVAL', 5),
        'EMAIL_NOTIFICATIONS': getattr(settings, 'ANALYTICS_EMAIL_NOTIFICATIONS', False),
        'WEBHOOK_NOTIFICATIONS': getattr(settings, 'ANALYTICS_WEBHOOK_NOTIFICATIONS', False),
    },
    
    # تنظیمات پاک‌سازی داده‌ها
    'DATA_RETENTION': {
        'METRICS_DAYS': getattr(settings, 'ANALYTICS_METRICS_RETENTION_DAYS', 30),
        'USER_ACTIVITY_DAYS': getattr(settings, 'ANALYTICS_USER_ACTIVITY_RETENTION_DAYS', 90),
        'PERFORMANCE_METRICS_DAYS': getattr(settings, 'ANALYTICS_PERFORMANCE_RETENTION_DAYS', 30),
        'BUSINESS_METRICS_DAYS': getattr(settings, 'ANALYTICS_BUSINESS_METRICS_RETENTION_DAYS', 365),
        'ALERTS_DAYS': getattr(settings, 'ANALYTICS_ALERTS_RETENTION_DAYS', 90),
    },
    
    # تنظیمات گزارش‌گیری
    'REPORTING': {
        'DAILY_REPORTS': getattr(settings, 'ANALYTICS_DAILY_REPORTS', True),
        'WEEKLY_REPORTS': getattr(settings, 'ANALYTICS_WEEKLY_REPORTS', False),
        'MONTHLY_REPORTS': getattr(settings, 'ANALYTICS_MONTHLY_REPORTS', False),
        'REPORT_EMAIL_RECIPIENTS': getattr(settings, 'ANALYTICS_REPORT_EMAIL_RECIPIENTS', []),
    },
    
    # تنظیمات Celery Tasks
    'CELERY_TASKS': {
        'ALERT_CHECK_SCHEDULE': getattr(settings, 'ANALYTICS_ALERT_CHECK_SCHEDULE', 300.0),  # 5 دقیقه
        'HOURLY_METRICS_SCHEDULE': getattr(settings, 'ANALYTICS_HOURLY_METRICS_SCHEDULE', 3600.0),  # 1 ساعت
        'DAILY_METRICS_SCHEDULE': getattr(settings, 'ANALYTICS_DAILY_METRICS_SCHEDULE', 86400.0),  # 24 ساعت
        'CLEANUP_SCHEDULE': getattr(settings, 'ANALYTICS_CLEANUP_SCHEDULE', 86400.0),  # 24 ساعت
    },
}