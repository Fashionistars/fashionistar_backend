"""
تسک‌های Celery برای اپلیکیشن DevOps
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

from .models import HealthCheck, ServiceMonitoring, EnvironmentConfig
from .services.health_service import HealthService

logger = logging.getLogger(__name__)


@shared_task
def run_health_checks():
    """
    اجرای health check های دوره‌ای برای تمام سرویس‌های فعال
    """
    logger.info("شروع health check های دوره‌ای")
    
    current_time = timezone.now()
    total_checks = 0
    successful_checks = 0
    
    # دریافت تمام سرویس‌های فعال
    active_services = ServiceMonitoring.objects.filter(is_active=True)
    
    for service in active_services:
        try:
            # بررسی آیا زمان check کردن رسیده یا نه
            last_check = HealthCheck.objects.filter(
                environment=service.environment,
                service_name=service.service_name
            ).order_by('-checked_at').first()
            
            should_check = True
            if last_check:
                time_since_last_check = (current_time - last_check.checked_at).total_seconds()
                should_check = time_since_last_check >= service.check_interval
            
            if should_check:
                logger.debug(f"اجرای health check برای {service.service_name}")
                
                # ایجاد health service
                health_service = HealthService(service.environment.name)
                
                # بررسی سرویس
                result = health_service.check_external_service(
                    service.health_check_url,
                    service.timeout
                )
                
                # ذخیره نتیجه
                health_service._save_health_check_result(service, result)
                
                total_checks += 1
                if result.get('status') == 'healthy':
                    successful_checks += 1
                    
        except Exception as e:
            logger.error(f"خطا در health check سرویس {service.service_name}: {str(e)}")
            
            # ذخیره خطا به عنوان health check ناموفق
            try:
                HealthCheck.objects.create(
                    environment=service.environment,
                    service_name=service.service_name,
                    endpoint_url=service.health_check_url,
                    status='critical',
                    error_message=str(e)
                )
            except Exception as save_error:
                logger.error(f"خطا در ذخیره health check: {str(save_error)}")
    
    logger.info(
        f"health check های دوره‌ای تکمیل شد. "
        f"کل: {total_checks}, موفق: {successful_checks}"
    )
    
    return {
        'total_checks': total_checks,
        'successful_checks': successful_checks,
        'timestamp': current_time.isoformat()
    }


@shared_task
def cleanup_old_health_checks(days_to_keep=30):
    """
    پاکسازی health check های قدیمی
    
    Args:
        days_to_keep: تعداد روزهایی که health check ها نگه داشته شوند
    """
    logger.info(f"شروع پاکسازی health check های بیشتر از {days_to_keep} روز")
    
    cutoff_date = timezone.now() - timedelta(days=days_to_keep)
    
    deleted_count, _ = HealthCheck.objects.filter(
        checked_at__lt=cutoff_date
    ).delete()
    
    logger.info(f"{deleted_count} health check قدیمی پاک شد")
    
    return {
        'deleted_count': deleted_count,
        'cutoff_date': cutoff_date.isoformat()
    }


@shared_task
def generate_uptime_report(environment_name, hours=24):
    """
    تولید گزارش uptime برای محیط مشخص
    
    Args:
        environment_name: نام محیط
        hours: بازه زمانی به ساعت
    """
    logger.info(f"تولید گزارش uptime برای محیط {environment_name}")
    
    try:
        environment = EnvironmentConfig.objects.get(
            name=environment_name,
            is_active=True
        )
    except EnvironmentConfig.DoesNotExist:
        logger.error(f"محیط {environment_name} یافت نشد")
        return {'error': f'محیط {environment_name} یافت نشد'}
    
    health_service = HealthService(environment_name)
    
    # دریافت تمام سرویس‌های محیط
    services = ServiceMonitoring.objects.filter(
        environment=environment,
        is_active=True
    )
    
    report = {
        'environment': environment_name,
        'period_hours': hours,
        'generated_at': timezone.now().isoformat(),
        'services': []
    }
    
    for service in services:
        uptime_data = health_service.get_service_uptime(service.service_name, hours)
        report['services'].append(uptime_data)
    
    logger.info(f"گزارش uptime برای {len(services)} سرویس تولید شد")
    
    return report


@shared_task
def check_deployment_status():
    """
    بررسی وضعیت deployment های در حال اجرا
    """
    from .models import DeploymentHistory
    
    logger.info("بررسی deployment های در حال اجرا")
    
    # deployment هایی که بیش از 30 دقیقه در حال اجرا هستند
    timeout_threshold = timezone.now() - timedelta(minutes=30)
    
    stuck_deployments = DeploymentHistory.objects.filter(
        status__in=['pending', 'running'],
        started_at__lt=timeout_threshold
    )
    
    for deployment in stuck_deployments:
        logger.warning(
            f"Deployment {deployment.id} در محیط {deployment.environment.name} "
            f"بیش از 30 دقیقه در حال اجرا است"
        )
        
        # می‌توان deployment را به عنوان failed علامت‌گذاری کرد
        # یا اعلان ارسال کرد
    
    return {
        'stuck_deployments': stuck_deployments.count(),
        'checked_at': timezone.now().isoformat()
    }


@shared_task
def backup_deployment_logs():
    """
    پشتیبان‌گیری از لاگ‌های deployment
    """
    from .models import DeploymentHistory
    import json
    from django.conf import settings
    import os
    
    logger.info("شروع پشتیبان‌گیری لاگ‌های deployment")
    
    # تنها deployment های آخر 7 روز
    since_date = timezone.now() - timedelta(days=7)
    
    deployments = DeploymentHistory.objects.filter(
        started_at__gte=since_date,
        deployment_logs__isnull=False
    ).exclude(deployment_logs='')
    
    backup_data = []
    
    for deployment in deployments:
        backup_data.append({
            'id': str(deployment.id),
            'environment': deployment.environment.name,
            'version': deployment.version,
            'status': deployment.status,
            'started_at': deployment.started_at.isoformat(),
            'completed_at': deployment.completed_at.isoformat() if deployment.completed_at else None,
            'logs': deployment.deployment_logs
        })
    
    # ذخیره در فایل
    backup_dir = getattr(settings, 'BACKUP_DIR', '/tmp/helssa_backups')
    os.makedirs(backup_dir, exist_ok=True)
    
    backup_filename = f"deployment_logs_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"پشتیبان‌گیری {len(backup_data)} deployment در {backup_path} ذخیره شد")
    
    return {
        'backed_up_count': len(backup_data),
        'backup_file': backup_path,
        'timestamp': timezone.now().isoformat()
    }


@shared_task
def monitor_system_resources():
    """
    مانیتورینگ منابع سیستم (CPU, Memory, Disk)
    """
    logger.info("مانیتورینگ منابع سیستم")
    
    health_service = HealthService()
    
    # بررسی منابع
    cpu_info = health_service.check_cpu()
    memory_info = health_service.check_memory()
    disk_info = health_service.check_disk_space()
    
    # ثبت هشدارها در صورت نیاز
    warnings = []
    
    if cpu_info.get('status') in ['warning', 'critical']:
        warnings.append(f"CPU usage: {cpu_info.get('cpu_percent', 0)}%")
    
    if memory_info.get('status') in ['warning', 'critical']:
        warnings.append(f"Memory usage: {memory_info.get('percent_used', 0)}%")
    
    if disk_info.get('status') in ['warning', 'critical']:
        warnings.append(f"Disk usage: {disk_info.get('percent_used', 0)}%")
    
    if warnings:
        logger.warning(f"هشدارهای منابع سیستم: {', '.join(warnings)}")
    
    return {
        'cpu': cpu_info,
        'memory': memory_info,
        'disk': disk_info,
        'warnings': warnings,
        'timestamp': timezone.now().isoformat()
    }