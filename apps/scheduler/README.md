# اپ Scheduler

اپ scheduler مسئول مدیریت و زمان‌بندی وظایف Celery در سیستم هلسا است.

## ویژگی‌ها

- **زمان‌بندی انعطاف‌پذیر**: پشتیبانی از انواع زمان‌بندی (یکبار، بازه‌ای، کرون)
- **مانیتورینگ کامل**: ثبت تمام جزئیات اجرا و عملکرد
- **سیستم هشدار**: تشخیص خودکار مشکلات و ارسال هشدار
- **API جامع**: دسترسی کامل به تمام قابلیت‌ها از طریق REST API
- **رابط Admin**: مدیریت آسان از طریق Django Admin

## نصب و راه‌اندازی

### 1. اضافه کردن به INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    'scheduler',
    'django_celery_beat',  # اختیاری
]
```

### 2. اضافه کردن URLs

```python
urlpatterns = [
    # ...
    path('api/scheduler/', include('scheduler.urls')),
]
```

### 3. اجرای migrations

```bash
python manage.py makemigrations scheduler
python manage.py migrate
```

### 4. راه‌اندازی Celery

```bash
# Worker
celery -A helssa worker -l info -Q default,scheduler,maintenance,monitoring,notifications

# Beat (برای وظایف periodic)
celery -A helssa beat -l info
```

## استفاده

### تعریف وظیفه جدید

```python
from scheduler.models import TaskDefinition

task_def = TaskDefinition.objects.create(
    name='پاکسازی فایل‌های موقت',
    task_path='files.tasks.cleanup_temp_files',
    task_type='cleanup',
    description='پاکسازی فایل‌های موقت قدیمی‌تر از 24 ساعت',
    queue_name='maintenance',
    default_params={'hours': 24}
)
```

### زمان‌بندی وظیفه

```python
from scheduler.models import ScheduledTask
from datetime import timedelta

# زمان‌بندی بازه‌ای (هر 6 ساعت)
scheduled_task = ScheduledTask.objects.create(
    task_definition=task_def,
    name='پاکسازی روزانه فایل‌های موقت',
    schedule_type='interval',
    interval_seconds=6 * 60 * 60,  # 6 ساعت
    priority=5
)

# زمان‌بندی کرون (هر روز ساعت 2 صبح)
scheduled_task = ScheduledTask.objects.create(
    task_definition=task_def,
    name='پاکسازی شبانه',
    schedule_type='cron',
    cron_expression='0 2 * * *',
    priority=3
)
```

### اجرای دستی

```python
from scheduler.tasks import execute_task

# اجرای مستقیم
result = execute_task.delay(
    execution_id='...',
    task_path='files.tasks.cleanup_temp_files',
    params={'hours': 24}
)
```

## API Endpoints

### Task Definitions

- `GET /api/scheduler/definitions/` - لیست تعاریف
- `POST /api/scheduler/definitions/` - ایجاد تعریف جدید
- `GET /api/scheduler/definitions/{id}/` - جزئیات تعریف
- `POST /api/scheduler/definitions/{id}/execute/` - اجرای دستی

### Scheduled Tasks

- `GET /api/scheduler/scheduled/` - لیست وظایف زمان‌بندی شده
- `POST /api/scheduler/scheduled/` - ایجاد زمان‌بندی جدید
- `POST /api/scheduler/scheduled/{id}/toggle_status/` - فعال/غیرفعال کردن
- `POST /api/scheduler/scheduled/{id}/run_now/` - اجرای فوری

### Executions

- `GET /api/scheduler/executions/` - سوابق اجرا
- `GET /api/scheduler/executions/{id}/` - جزئیات اجرا با لاگ‌ها
- `GET /api/scheduler/executions/{id}/status/` - وضعیت Celery
- `POST /api/scheduler/executions/{id}/cancel/` - لغو اجرا

### Alerts

- `GET /api/scheduler/alerts/` - لیست هشدارها
- `POST /api/scheduler/alerts/{id}/resolve/` - حل کردن هشدار
- `GET /api/scheduler/alerts/summary/` - خلاصه وضعیت

### Statistics

- `GET /api/scheduler/statistics/overview/` - آمار کلی
- `GET /api/scheduler/statistics/performance/` - گزارش عملکرد

## مدل‌های داده

### TaskDefinition
تعریف وظایف قابل اجرا در سیستم

### ScheduledTask
وظایف زمان‌بندی شده با انواع مختلف schedule

### TaskExecution
سابقه هر بار اجرای وظیفه

### TaskLog
لاگ‌های جزئی در حین اجرا

### TaskAlert
هشدارهای تولید شده برای مشکلات

## تنظیمات

```python
# scheduler/settings.py

# Celery
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

# Scheduler
SCHEDULER_CLEANUP_DAYS = 30  # نگهداری سوابق
SCHEDULER_ALERT_THRESHOLD_MINUTES = 5  # آستانه هشدار
SCHEDULER_DEFAULT_MAX_RETRIES = 3  # تلاش مجدد
```

## نکات امنیتی

- تنها کاربران admin می‌توانند وظایف تعریف کنند
- task_path باید به توابع معتبر اشاره کند
- پارامترها باید validate شوند
- لاگ‌ها ممکن است حاوی اطلاعات حساس باشند

## توسعه

برای اضافه کردن task جدید:

1. تابع را در اپ مربوطه تعریف کنید
2. از decorator مناسب استفاده کنید
3. در TaskDefinition ثبت کنید
4. زمان‌بندی مورد نظر را تنظیم کنید

```python
# example_app/tasks.py
from celery import shared_task

@shared_task
def my_custom_task(param1, param2):
    """وظیفه سفارشی"""
    # کد وظیفه
    return result
```