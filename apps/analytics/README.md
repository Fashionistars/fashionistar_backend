# اپ Analytics

این اپ برای جمع‌آوری، ذخیره‌سازی و تحلیل متریک‌های سیستم، فعالیت‌های کاربران و عملکرد API طراحی شده است.

## ویژگی‌ها

### متریک‌ها
- ثبت انواع مختلف متریک (counter, gauge, histogram, timer)
- برچسب‌گذاری متریک‌ها برای دسته‌بندی
- API برای ثبت متریک‌های سفارشی

### ردیابی فعالیت کاربران
- ثبت خودکار فعالیت‌های کاربران
- ردیابی IP، User Agent و اطلاعات جلسه
- تحلیل الگوهای استفاده

### متریک‌های عملکرد
- ردیابی خودکار زمان پاسخ API ها
- ثبت کدهای وضعیت و خطاها
- تحلیل کندترین endpoints

### هشدارها
- تعریف قوانین هشدار بر اساس آستانه
- هشدارهای خودکار برای مشکلات سیستم
- سطوح مختلف اهمیت

### گزارش‌گیری
- متریک‌های کسب و کار
- گزارش‌های روزانه، هفتگی و ماهانه
- تحلیل‌های پیشرفته

## نصب و راه‌اندازی

### 1. اضافه کردن به INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    'analytics',
    # ...
]
```

### 2. اضافه کردن Middleware (اختیاری)

برای ردیابی خودکار عملکرد و فعالیت کاربران:

```python
MIDDLEWARE = [
    # ...
    'analytics.middleware.performance_tracking.PerformanceTrackingMiddleware',
    'analytics.middleware.user_activity.UserActivityTrackingMiddleware',
    # ...
]
```

### 3. تنظیمات Analytics

```python
# فعال/غیرفعال کردن Analytics
ANALYTICS_ENABLED = True

# تنظیمات ردیابی عملکرد
ANALYTICS_PERFORMANCE_TRACKING_ENABLED = True
ANALYTICS_PERFORMANCE_EXCLUDE_PATHS = ['/admin/', '/static/', '/media/']

# تنظیمات ردیابی فعالیت کاربران
ANALYTICS_USER_ACTIVITY_TRACKING_ENABLED = True
ANALYTICS_TRACK_GET_REQUESTS = False

# تنظیمات هشدارها
ANALYTICS_ALERTS_ENABLED = True
ANALYTICS_ALERT_CHECK_INTERVAL = 5  # دقیقه

# تنظیمات نگهداری داده‌ها
ANALYTICS_METRICS_RETENTION_DAYS = 30
ANALYTICS_USER_ACTIVITY_RETENTION_DAYS = 90
```

### 4. اضافه کردن URLها

در فایل `urls.py` اصلی:

```python
urlpatterns = [
    # ...
    path('api/analytics/', include('analytics.urls')),
    # ...
]
```

### 5. مایگریشن

```bash
python manage.py makemigrations analytics
python manage.py migrate
```

### 6. تنظیم Celery Tasks (اختیاری)

برای فعال‌سازی کارهای زمان‌بندی شده:

```python
CELERY_BEAT_SCHEDULE = {
    'analytics-check-alerts': {
        'task': 'analytics.tasks.check_alert_rules',
        'schedule': 300.0,  # هر 5 دقیقه
    },
    'analytics-hourly-metrics': {
        'task': 'analytics.tasks.calculate_hourly_metrics',
        'schedule': 3600.0,  # هر ساعت
    },
    'analytics-daily-metrics': {
        'task': 'analytics.tasks.calculate_daily_metrics',
        'schedule': crontab(hour=1, minute=0),  # هر روز ساعت 1 صبح
    },
    'analytics-cleanup': {
        'task': 'analytics.tasks.cleanup_old_metrics',
        'schedule': crontab(hour=2, minute=0),  # هر روز ساعت 2 صبح
    },
}
```

## استفاده

### ثبت متریک سفارشی

```python
from analytics.services import AnalyticsService

analytics = AnalyticsService()

# ثبت متریک ساده
analytics.record_metric('user_login_count', 1, 'counter')

# ثبت متریک با برچسب
analytics.record_metric(
    'api_response_time', 
    150.5, 
    'timer',
    tags={'endpoint': '/api/users/', 'method': 'GET'}
)
```

### ثبت فعالیت کاربر

```python
analytics.record_user_activity(
    user=request.user,
    action='profile_update',
    resource='user_profile',
    resource_id=user.id,
    request=request
)
```

### استفاده از Decorators

```python
from analytics.utils.decorators import track_performance, track_calls

@track_performance('custom_function_timer')
@track_calls('custom_function_calls')
def my_important_function():
    # کد شما
    pass
```

### ایجاد قانون هشدار

```python
from analytics.models import AlertRule

AlertRule.objects.create(
    name='High API Response Time',
    metric_name='api_response_time_avg',
    operator='gt',
    threshold=1000.0,  # میلی‌ثانیه
    severity='high',
    description='هشدار زمانی که میانگین زمان پاسخ API بیش از 1 ثانیه باشد'
)
```

## API Endpoints

### متریک‌ها
- `GET /api/analytics/metrics/` - لیست متریک‌ها
- `POST /api/analytics/record-metric/` - ثبت متریک جدید

### فعالیت‌های کاربران
- `GET /api/analytics/user-activities/` - لیست فعالیت‌های کاربران
- `GET /api/analytics/user-analytics/` - تحلیل‌های کاربر

### متریک‌های عملکرد
- `GET /api/analytics/performance-metrics/` - لیست متریک‌های عملکرد
- `GET /api/analytics/performance-analytics/` - تحلیل‌های عملکرد

### هشدارها
- `GET /api/analytics/alerts/` - لیست هشدارها
- `GET /api/analytics/alert-rules/` - لیست قوانین هشدار
- `POST /api/analytics/check-alerts/` - بررسی دستی هشدارها

### گزارش‌ها
- `GET /api/analytics/system-overview/` - بررسی کلی سیستم
- `POST /api/analytics/calculate-business-metrics/` - محاسبه متریک‌های کسب و کار

## نمونه استفاده در Production

### 1. مانیتورینگ Performance
```python
# تنظیم هشدار برای زمان پاسخ بالا
AlertRule.objects.create(
    name='High Response Time Alert',
    metric_name='avg_response_time_ms',
    operator='gt',
    threshold=500,
    severity='medium'
)
```

### 2. ردیابی تعداد خطاها
```python
# تنظیم هشدار برای نرخ خطای بالا
AlertRule.objects.create(
    name='High Error Rate Alert',
    metric_name='error_rate_percent',
    operator='gt',
    threshold=5.0,
    severity='high'
)
```

### 3. مانیتورینگ فعالیت کاربران
```python
# دریافت تحلیل‌های فعالیت کاربران
analytics = AnalyticsService()
user_analytics = analytics.get_user_analytics(days=7)
print(f"کل فعالیت‌ها: {user_analytics['total_activities']}")
print(f"کاربران فعال: {user_analytics['unique_users']}")
```

## نکات مهم

1. **عملکرد**: ردیابی خودکار با استفاده از Celery Tasks انجام می‌شود تا عملکرد سیستم تحت تأثیر قرار نگیرد.

2. **حریم خصوصی**: اطلاعات حساس کاربران ذخیره نمی‌شود، فقط metadata عمومی ثبت می‌گردد.

3. **پاک‌سازی**: داده‌های قدیمی به صورت خودکار پاک می‌شوند تا از پر شدن دیتابیس جلوگیری شود.

4. **مقیاس‌پذیری**: سیستم برای حجم بالای داده طراحی شده و از indexهای مناسب استفاده می‌کند.

5. **قابلیت کنترل**: تمام ویژگی‌ها قابل فعال/غیرفعال کردن هستند.