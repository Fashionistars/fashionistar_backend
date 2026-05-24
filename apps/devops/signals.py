"""
سیگنال‌های اپلیکیشن DevOps
"""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
from .models import DeploymentHistory, HealthCheck, ServiceMonitoring
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=DeploymentHistory)
def deployment_status_changed(sender, instance, created, **kwargs):
    """
    سیگنال تغییر وضعیت deployment
    """
    if not created and instance.status in ['success', 'failed']:
        logger.info(
            f"Deployment {instance.id} در محیط {instance.environment.name} "
            f"با وضعیت {instance.status} تکمیل شد"
        )
        
        # در صورت موفقیت deployment، می‌توان اعلان‌هایی ارسال کرد
        if instance.status == 'success':
            logger.info(f"Deployment موفق نسخه {instance.version}")
            # TODO: ارسال اعلان موفقیت
            
        elif instance.status == 'failed':
            logger.error(f"Deployment ناموفق نسخه {instance.version}")
            # TODO: ارسال اعلان خطا


@receiver(post_save, sender=HealthCheck)
def health_check_status_changed(sender, instance, created, **kwargs):
    """
    سیگنال تغییر وضعیت health check
    """
    if created and instance.status == 'critical':
        # سرویس در وضعیت بحرانی
        service_monitoring = ServiceMonitoring.objects.filter(
            environment=instance.environment,
            service_name=instance.service_name,
            alert_on_failure=True
        ).first()
        
        if service_monitoring:
            logger.critical(
                f"سرویس {instance.service_name} در محیط {instance.environment.name} "
                f"در وضعیت بحرانی قرار گرفت: {instance.error_message}"
            )
            # TODO: ارسال alert
    
    elif created and instance.status == 'healthy':
        # بررسی اگر سرویس از وضعیت بحرانی به سالم برگشته
        previous_check = HealthCheck.objects.filter(
            environment=instance.environment,
            service_name=instance.service_name,
            checked_at__lt=instance.checked_at
        ).order_by('-checked_at').first()
        
        if previous_check and previous_check.status == 'critical':
            logger.info(
                f"سرویس {instance.service_name} در محیط {instance.environment.name} "
                f"به وضعیت سالم برگشت"
            )
            # TODO: ارسال اعلان بهبود


@receiver(pre_delete, sender=ServiceMonitoring)
def service_monitoring_deleted(sender, instance, **kwargs):
    """
    سیگنال حذف سرویس مانیتورینگ
    """
    logger.info(
        f"سرویس مانیتورینگ {instance.service_name} "
        f"در محیط {instance.environment.name} حذف شد"
    )