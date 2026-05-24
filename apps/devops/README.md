# اپلیکیشن DevOps - مدیریت زیرساخت و استقرار

این اپلیکیشن برای مدیریت زیرساخت، deployment، مانیتورینگ و CI/CD در پلتفرم هلسا طراحی شده است.

## 📋 ویژگی‌ها

### مدیریت محیط‌ها (Environment Management)
- تعریف و مدیریت محیط‌های مختلف (development, staging, production)
- مدیریت رمزهای رمزنگاری شده (Secrets Management)
- کنترل دسترسی و مجوزها

### مدیریت Docker و Container
- کنترل Docker containers
- مدیریت Docker Compose services
- مانیتورینگ وضعیت containers
- دریافت لاگ‌ها و آمار

### سیستم Deployment
- اجرای deployment خودکار
- پشتیبانی از Git branches مختلف
- قابلیت Rollback به نسخه‌های قبلی
- ثبت کامل لاگ‌های deployment

### Health Check و Monitoring
- بررسی دوره‌ای سلامت سرویس‌ها
- مانیتورینگ منابع سیستم (CPU, Memory, Disk)
- محاسبه Uptime و آمارهای عملکرد
- سیستم هشدار خودکار

### Management Commands
- دستورات CLI برای automation
- تنظیمات اولیه محیط‌ها
- اجرای deployment از command line
- گزارش‌گیری و مانیتورینگ

## 🚀 نصب و راه‌اندازی

### 1. اضافه کردن به INSTALLED_APPS

```python
# settings.py
INSTALLED_APPS = [
    # ... سایر اپلیکیشن‌ها
    'devops',
]
```

### 2. اجرای Migration ها

```bash
python manage.py makemigrations devops
python manage.py migrate
```

### 3. تنظیم URL ها

```python
# urls.py
urlpatterns = [
    # ... سایر URL ها
    path('devops/', include('devops.urls')),
]
```

### 4. تنظیمات اولیه محیط

```bash
# راه‌اندازی سریع محیط development
python manage.py setup_environment --environment development --type development --quick-setup

# راه‌اندازی از فایل تنظیمات
python manage.py setup_environment --config environments.json
```

## 📝 مثال فایل تنظیمات

```json
{
  "environments": [
    {
      "name": "production",
      "environment_type": "production",
      "description": "محیط تولید اصلی",
      "is_active": true
    },
    {
      "name": "staging", 
      "environment_type": "staging",
      "description": "محیط تست قبل از تولید",
      "is_active": true
    }
  ],
  "monitoring": [
    {
      "environment": "production",
      "service_name": "web",
      "service_type": "web",
      "health_check_url": "https://helssa.ir/health/",
      "check_interval": 300,
      "timeout": 30
    },
    {
      "environment": "production",
      "service_name": "database",
      "service_type": "database", 
      "health_check_url": "https://helssa.ir/health/",
      "check_interval": 600,
      "timeout": 15
    }
  ]
}
```

## 🛠️ استفاده از Management Commands

### Health Check
```bash
# بررسی سلامت کلی سیستم
python manage.py health_check

# بررسی محیط خاص
python manage.py health_check --environment production

# بررسی سرویس خاص
python manage.py health_check --environment production --service web

# خروجی JSON
python manage.py health_check --json --fail-on-error
```

### Deployment
```bash
# deployment جدید
python manage.py deploy --environment production --version v1.2.3

# deployment با تنظیمات خاص
python manage.py deploy -e staging -v v1.2.3 --branch develop --no-migrations

# rollback
python manage.py rollback --environment production --target-deployment-id abc-123-def
```

### مدیریت Docker
```bash
# مشاهده containers
python manage.py docker_manage --action ps

# راه‌اندازی مجدد container
python manage.py docker_manage --action restart --container web

# وضعیت Docker Compose
python manage.py docker_manage --action compose-status

# راه‌اندازی مجدد سرویس‌ها
python manage.py docker_manage --action compose-restart --services web worker
```

## 🔌 API Endpoints

### Health Check
- `GET /devops/health/` - بررسی سلامت کلی
- `GET /devops/health/{environment}/` - بررسی سلامت محیط خاص

### Docker Management
- `GET /devops/docker/containers/` - لیست containers
- `POST /devops/docker/containers/` - عملیات روی containers
- `GET /devops/docker/compose/` - وضعیت compose services
- `POST /devops/docker/compose/` - عملیات روی compose

### Deployment
- `POST /devops/deploy/` - شروع deployment جدید
- `POST /devops/rollback/` - rollback deployment

### Monitoring
- `GET /devops/uptime/{environment}/{service}/` - uptime سرویس
- `GET /devops/metrics/` - متریک‌های عملکرد سیستم
- `GET /devops/metrics/{environment}/` - متریک‌های محیط خاص

### ViewSets (CRUD)
- `/devops/api/environments/` - مدیریت محیط‌ها
- `/devops/api/deployments/` - تاریخچه deployments
- `/devops/api/health-checks/` - نتایج health checks
- `/devops/api/service-monitoring/` - تنظیمات مانیتورینگ

## 🔧 تنظیمات Celery

### اضافه کردن Tasks به Beat Schedule

```python
# settings.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Health checks هر 5 دقیقه
    'run-health-checks': {
        'task': 'devops.tasks.run_health_checks',
        'schedule': crontab(minute='*/5'),
    },
    
    # پاکسازی health checks قدیمی روزانه
    'cleanup-health-checks': {
        'task': 'devops.tasks.cleanup_old_health_checks',
        'schedule': crontab(hour=2, minute=0),  # ساعت 2 صبح
    },
    
    # مانیتورینگ منابع سیستم هر 10 دقیقه
    'monitor-system-resources': {
        'task': 'devops.tasks.monitor_system_resources',
        'schedule': crontab(minute='*/10'),
    },
    
    # بررسی deployment های گیر کرده هر ساعت
    'check-deployment-status': {
        'task': 'devops.tasks.check_deployment_status',
        'schedule': crontab(minute=0),  # ابتدای هر ساعت
    },
    
    # پشتیبان‌گیری لاگ‌های deployment روزانه
    'backup-deployment-logs': {
        'task': 'devops.tasks.backup_deployment_logs',
        'schedule': crontab(hour=3, minute=0),  # ساعت 3 صبح
    },
}
```

## 🧪 اجرای تست‌ها

```bash
# اجرای تمام تست‌های devops
python manage.py test devops

# اجرای تست‌های خاص
python manage.py test devops.tests.HealthServiceTestCase

# اجرای تست‌ها با coverage
coverage run --source='.' manage.py test devops
coverage report
coverage html
```

## 📊 مثال‌های استفاده

### 1. ایجاد محیط جدید

```python
from devops.models import EnvironmentConfig

# ایجاد محیط staging
staging_env = EnvironmentConfig.objects.create(
    name='staging',
    environment_type='staging', 
    description='محیط تست قبل از production'
)
```

### 2. تنظیم مانیتورینگ سرویس

```python
from devops.models import ServiceMonitoring

# اضافه کردن سرویس web به مانیتورینگ
web_monitoring = ServiceMonitoring.objects.create(
    environment=staging_env,
    service_name='web',
    service_type='web',
    health_check_url='https://staging.helssa.ir/health/',
    check_interval=300,  # هر 5 دقیقه
    timeout=30
)
```

### 3. اجرای deployment برنامه‌نویسی

```python
from devops.services.deployment_service import DeploymentService

# deployment به staging
deployment_service = DeploymentService('staging')
deployment = deployment_service.deploy(
    version='v1.2.3',
    branch='develop',
    user=request.user
)

print(f"Deployment status: {deployment.status}")
```

### 4. بررسی health check

```python
from devops.services.health_service import HealthService

# بررسی سلامت staging
health_service = HealthService('staging')
result = health_service.comprehensive_health_check()

print(f"Overall status: {result['overall_status']}")
for service, status in result['services'].items():
    print(f"{service}: {status['status']}")
```

## 🔒 امنیت

### رمزنگاری Secrets
- تمام secrets با کلید رمزنگاری Django رمزنگاری می‌شوند
- دسترسی به secrets محدود به کاربران مجاز است
- امکان تنظیم تاریخ انقضا برای secrets

### کنترل دسترسی
- تمام API ها نیاز به احراز هویت دارند
- Rate limiting برای جلوگیری از سوء استفاده
- لاگ کامل تمام عملیات

### Audit Trail
- ثبت کامل تاریخچه deployments
- لاگ تمام تغییرات در محیط‌ها
- ردیابی کاربران اجراکننده عملیات

## 📈 مانیتورینگ و هشدارها

### متریک‌های کلیدی
- Deployment success rate
- Service uptime percentage  
- Response time averages
- Resource utilization (CPU/Memory/Disk)

### سیستم هشدار
- اعلان خرابی سرویس‌ها
- هشدار استفاده بالای منابع
- اطلاع deployment های ناموفق
- آگاهی از انقضای secrets

## 🤝 مشارکت

برای مشارکت در توسعه:

1. کد خود را بر اساس استانداردهای تعریف شده بنویسید
2. تست‌های مناسب اضافه کنید
3. مستندات را به‌روزرسانی کنید
4. Pull Request ارسال کنید

## 📚 منابع اضافی

- [مستندات Django](https://docs.djangoproject.com/)
- [Docker Documentation](https://docs.docker.com/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [REST Framework](https://www.django-rest-framework.org/)

---

© 2024 Helssa Platform - تمام حقوق محفوظ است