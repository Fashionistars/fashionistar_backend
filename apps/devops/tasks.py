# apps/devops/tasks.py
"""
Celery tasks for the DevOps application.
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
    Run periodic health checks for all active monitored services.
    """
    logger.info("Starting periodic health checks")
    
    current_time = timezone.now()
    total_checks = 0
    successful_checks = 0
    
    active_services = ServiceMonitoring.objects.filter(is_active=True)
    
    for service in active_services:
        try:
            last_check = HealthCheck.objects.filter(
                environment=service.environment,
                service_name=service.service_name
            ).order_by('-checked_at').first()
            
            should_check = True
            if last_check:
                time_since_last_check = (current_time - last_check.checked_at).total_seconds()
                should_check = time_since_last_check >= service.check_interval
            
            if should_check:
                logger.debug(f"Running health check for {service.service_name}")
                
                health_service = HealthService(service.environment.name)
                result = health_service.check_external_service(
                    service.health_check_url,
                    service.timeout
                )
                
                health_service._save_health_check_result(service, result)
                
                total_checks += 1
                if result.get('status') == 'healthy':
                    successful_checks += 1
                    
        except Exception as e:
            logger.error(f"Error checking health for service {service.service_name}: {str(e)}")
            
            try:
                HealthCheck.objects.create(
                    environment=service.environment,
                    service_name=service.service_name,
                    endpoint_url=service.health_check_url,
                    status='critical',
                    error_message=str(e)
                )
            except Exception as save_error:
                logger.error(f"Error saving health check error record: {str(save_error)}")
    
    logger.info(
        f"Periodic health checks completed. "
        f"Total checks: {total_checks}, Successful: {successful_checks}"
    )
    
    return {
        'total_checks': total_checks,
        'successful_checks': successful_checks,
        'timestamp': current_time.isoformat()
    }


@shared_task
def cleanup_old_health_checks(days_to_keep=30):
    """
    Cleanup old health check records from the database.
    
    Args:
        days_to_keep: Number of days of health checks to retain.
    """
    logger.info(f"Starting cleanup of health checks older than {days_to_keep} days")
    
    cutoff_date = timezone.now() - timedelta(days=days_to_keep)
    deleted_count, _ = HealthCheck.objects.filter(
        checked_at__lt=cutoff_date
    ).delete()
    
    logger.info(f"Cleaned up {deleted_count} old health check records")
    
    return {
        'deleted_count': deleted_count,
        'cutoff_date': cutoff_date.isoformat()
    }


@shared_task
def generate_uptime_report(environment_name, hours=24):
    """
    Generate service uptime report for a specified environment.
    
    Args:
        environment_name: Target environment name.
        hours: Uptime time range in hours.
    """
    logger.info(f"Generating uptime report for environment {environment_name}")
    
    try:
        environment = EnvironmentConfig.objects.get(
            name=environment_name,
            is_active=True
        )
    except EnvironmentConfig.DoesNotExist:
        logger.error(f"Environment {environment_name} not found")
        return {'error': f'Environment {environment_name} not found'}
    
    health_service = HealthService(environment_name)
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
    
    logger.info(f"Uptime report generated for {len(services)} services")
    
    return report


@shared_task
def check_deployment_status():
    """
    Monitor and check for stuck deployment runs.
    """
    from .models import DeploymentHistory
    
    logger.info("Checking running deployments status")
    
    # Stuck if deployment has been running for more than 30 minutes
    timeout_threshold = timezone.now() - timedelta(minutes=30)
    
    stuck_deployments = DeploymentHistory.objects.filter(
        status__in=['pending', 'running'],
        started_at__lt=timeout_threshold
    )
    
    for deployment in stuck_deployments:
        logger.warning(
            f"Deployment {deployment.id} in environment {deployment.environment.name} "
            f"has been running for over 30 minutes"
        )
    
    return {
        'stuck_deployments': stuck_deployments.count(),
        'checked_at': timezone.now().isoformat()
    }


@shared_task
def backup_deployment_logs():
    """
    Backup deployment execution logs to a file.
    """
    from .models import DeploymentHistory
    import json
    from django.conf import settings
    import os
    
    logger.info("Starting backup of deployment logs")
    
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
    
    backup_dir = getattr(settings, 'BACKUP_DIR', '/tmp/fashionistar_backups')
    os.makedirs(backup_dir, exist_ok=True)
    
    backup_filename = f"deployment_logs_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Backed up {len(backup_data)} deployments to {backup_path}")
    
    return {
        'backed_up_count': len(backup_data),
        'backup_file': backup_path,
        'timestamp': timezone.now().isoformat()
    }


@shared_task
def monitor_system_resources():
    """
    Monitor core system resource metrics (CPU, Memory, Disk).
    """
    logger.info("Monitoring core system resources")
    
    health_service = HealthService()
    cpu_info = health_service.check_cpu()
    memory_info = health_service.check_memory()
    disk_info = health_service.check_disk_space()
    
    warnings = []
    
    if cpu_info.get('status') in ['warning', 'critical']:
        warnings.append(f"CPU usage: {cpu_info.get('cpu_percent', 0)}%")
    
    if memory_info.get('status') in ['warning', 'critical']:
        warnings.append(f"Memory usage: {memory_info.get('percent_used', 0)}%")
    
    if disk_info.get('status') in ['warning', 'critical']:
        warnings.append(f"Disk usage: {disk_info.get('percent_used', 0)}%")
    
    if warnings:
        logger.warning(f"System resource warnings: {', '.join(warnings)}")
    
    return {
        'cpu': cpu_info,
        'memory': memory_info,
        'disk': disk_info,
        'warnings': warnings,
        'timestamp': timezone.now().isoformat()
    }