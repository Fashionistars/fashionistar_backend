"""
سرویس بررسی سلامت سیستم و مانیتورینگ
"""
import requests
import time
import psutil
import subprocess
from typing import Dict, List, Optional, Tuple, Any
from django.db import connection
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
import logging
import json

from ..models import HealthCheck, ServiceMonitoring, EnvironmentConfig

logger = logging.getLogger(__name__)


class HealthService:
    """سرویس بررسی سلامت سیستم"""
    
    def __init__(self, environment_name: Optional[str] = None):
        """
        تنظیم محیط برای health check
        
        Args:
            environment_name: نام محیط (اختیاری)
        """
        self.environment = None
        if environment_name:
            try:
                self.environment = EnvironmentConfig.objects.get(
                    name=environment_name,
                    is_active=True
                )
            except EnvironmentConfig.DoesNotExist:
                logger.warning(f"محیط {environment_name} یافت نشد")
    
    def check_database(self) -> Dict[str, Any]:
        """بررسی سلامت پایگاه داده"""
        start_time = time.time()
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            
            response_time = (time.time() - start_time) * 1000
            
            # دریافت اطلاعات اضافی پایگاه داده
            with connection.cursor() as cursor:
                cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                connections = cursor.fetchone()
                
                cursor.execute("SHOW STATUS LIKE 'Uptime'")
                uptime = cursor.fetchone()
            
            return {
                'status': 'healthy',
                'response_time': round(response_time, 2),
                'connections': connections[1] if connections else 'unknown',
                'uptime': uptime[1] if uptime else 'unknown',
                'engine': connection.vendor,
            }
            
        except Exception as e:
            logger.error(f"خطا در بررسی پایگاه داده: {str(e)}")
            return {
                'status': 'critical',
                'error': str(e),
                'response_time': (time.time() - start_time) * 1000
            }
    
    def check_cache(self) -> Dict[str, Any]:
        """بررسی سلامت کش (Redis)"""
        start_time = time.time()
        
        try:
            # تست ساده کش
            test_key = f'health_check_{int(time.time())}'
            cache.set(test_key, 'OK', 10)
            value = cache.get(test_key)
            cache.delete(test_key)
            
            response_time = (time.time() - start_time) * 1000
            
            if value == 'OK':
                # دریافت اطلاعات Redis
                from django_redis import get_redis_connection
                redis_conn = get_redis_connection("default")
                info = redis_conn.info()
                
                return {
                    'status': 'healthy',
                    'response_time': round(response_time, 2),
                    'version': info.get('redis_version'),
                    'used_memory': info.get('used_memory_human'),
                    'connected_clients': info.get('connected_clients'),
                    'uptime': info.get('uptime_in_seconds'),
                }
            else:
                return {
                    'status': 'critical',
                    'error': 'تست کش ناموفق بود',
                    'response_time': round(response_time, 2)
                }
                
        except Exception as e:
            logger.error(f"خطا در بررسی کش: {str(e)}")
            return {
                'status': 'critical',
                'error': str(e),
                'response_time': (time.time() - start_time) * 1000
            }
    
    def check_disk_space(self) -> Dict[str, Any]:
        """بررسی فضای دیسک"""
        try:
            disk_usage = psutil.disk_usage('/')
            total = disk_usage.total
            used = disk_usage.used
            free = disk_usage.free
            percent = (used / total) * 100
            
            # تعیین وضعیت بر اساس درصد استفاده
            if percent < 80:
                status = 'healthy'
            elif percent < 90:
                status = 'warning'
            else:
                status = 'critical'
            
            return {
                'status': status,
                'total_gb': round(total / (1024**3), 2),
                'used_gb': round(used / (1024**3), 2),
                'free_gb': round(free / (1024**3), 2),
                'percent_used': round(percent, 2),
            }
            
        except Exception as e:
            logger.error(f"خطا در بررسی فضای دیسک: {str(e)}")
            return {
                'status': 'unknown',
                'error': str(e)
            }
    
    def check_memory(self) -> Dict[str, Any]:
        """بررسی حافظه سیستم"""
        try:
            memory = psutil.virtual_memory()
            percent = memory.percent
            
            # تعیین وضعیت بر اساس درصد استفاده
            if percent < 80:
                status = 'healthy'
            elif percent < 90:
                status = 'warning'
            else:
                status = 'critical'
            
            return {
                'status': status,
                'total_gb': round(memory.total / (1024**3), 2),
                'used_gb': round(memory.used / (1024**3), 2),
                'available_gb': round(memory.available / (1024**3), 2),
                'percent_used': round(percent, 2),
            }
            
        except Exception as e:
            logger.error(f"خطا در بررسی حافظه: {str(e)}")
            return {
                'status': 'unknown',
                'error': str(e)
            }
    
    def check_cpu(self) -> Dict[str, Any]:
        """بررسی CPU سیستم"""
        try:
            # دریافت درصد CPU در 1 ثانیه
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
            
            # تعیین وضعیت بر اساس بار CPU
            if cpu_percent < 70:
                status = 'healthy'
            elif cpu_percent < 85:
                status = 'warning'
            else:
                status = 'critical'
            
            result = {
                'status': status,
                'cpu_percent': round(cpu_percent, 2),
                'cpu_count': cpu_count,
            }
            
            if load_avg:
                result['load_avg'] = [round(x, 2) for x in load_avg]
            
            return result
            
        except Exception as e:
            logger.error(f"خطا در بررسی CPU: {str(e)}")
            return {
                'status': 'unknown',
                'error': str(e)
            }
    
    def check_external_service(self, url: str, timeout: int = 10) -> Dict[str, Any]:
        """بررسی سلامت سرویس خارجی"""
        start_time = time.time()
        
        try:
            response = requests.get(url, timeout=timeout)
            response_time = (time.time() - start_time) * 1000
            
            # تعیین وضعیت بر اساس کد پاسخ و زمان
            if response.status_code == 200:
                if response_time < 1000:
                    status = 'healthy'
                elif response_time < 5000:
                    status = 'warning'
                else:
                    status = 'critical'
            else:
                status = 'critical'
            
            return {
                'status': status,
                'status_code': response.status_code,
                'response_time': round(response_time, 2),
                'url': url,
            }
            
        except requests.exceptions.Timeout:
            return {
                'status': 'critical',
                'error': 'Timeout',
                'response_time': timeout * 1000,
                'url': url,
            }
        except Exception as e:
            logger.error(f"خطا در بررسی سرویس {url}: {str(e)}")
            return {
                'status': 'critical',
                'error': str(e),
                'response_time': (time.time() - start_time) * 1000,
                'url': url,
            }
    
    def comprehensive_health_check(self) -> Dict[str, Any]:
        """بررسی جامع سلامت سیستم"""
        start_time = time.time()
        
        results = {
            'timestamp': timezone.now().isoformat(),
            'overall_status': 'healthy',
            'services': {}
        }
        
        # بررسی پایگاه داده
        db_result = self.check_database()
        results['services']['database'] = db_result
        
        # بررسی کش
        cache_result = self.check_cache()
        results['services']['cache'] = cache_result
        
        # بررسی منابع سیستم
        results['services']['disk'] = self.check_disk_space()
        results['services']['memory'] = self.check_memory()
        results['services']['cpu'] = self.check_cpu()
        
        # بررسی سرویس‌های مانیتور شده
        if self.environment:
            monitored_services = ServiceMonitoring.objects.filter(
                environment=self.environment,
                is_active=True
            )
            
            for service in monitored_services:
                service_result = self.check_external_service(
                    service.health_check_url,
                    service.timeout
                )
                results['services'][service.service_name] = service_result
                
                # ذخیره نتیجه در پایگاه داده
                self._save_health_check_result(service, service_result)
        
        # تعیین وضعیت کلی
        critical_count = sum(1 for s in results['services'].values() 
                           if s.get('status') == 'critical')
        warning_count = sum(1 for s in results['services'].values() 
                          if s.get('status') == 'warning')
        
        if critical_count > 0:
            results['overall_status'] = 'critical'
        elif warning_count > 0:
            results['overall_status'] = 'warning'
        
        # زمان کل بررسی
        results['total_check_time'] = round((time.time() - start_time) * 1000, 2)
        
        return results
    
    def _save_health_check_result(self, service: ServiceMonitoring, result: Dict[str, Any]):
        """ذخیره نتیجه health check در پایگاه داده"""
        try:
            HealthCheck.objects.create(
                environment=service.environment,
                service_name=service.service_name,
                endpoint_url=service.health_check_url,
                status=result.get('status', 'unknown'),
                response_time=result.get('response_time'),
                status_code=result.get('status_code'),
                response_data=result,
                error_message=result.get('error', '')
            )
        except Exception as e:
            logger.error(f"خطا در ذخیره نتیجه health check: {str(e)}")
    
    def get_service_uptime(self, service_name: str, hours: int = 24) -> Dict[str, Any]:
        """محاسبه uptime سرویس در بازه زمانی مشخص"""
        if not self.environment:
            return {'error': 'محیط مشخص نشده'}
        
        try:
            from_time = timezone.now() - timezone.timedelta(hours=hours)
            
            checks = HealthCheck.objects.filter(
                environment=self.environment,
                service_name=service_name,
                checked_at__gte=from_time
            ).order_by('checked_at')
            
            if not checks.exists():
                return {
                    'service_name': service_name,
                    'uptime_percent': 0,
                    'total_checks': 0,
                    'hours': hours
                }
            
            total_checks = checks.count()
            healthy_checks = checks.filter(status='healthy').count()
            uptime_percent = (healthy_checks / total_checks) * 100
            
            # آخرین وضعیت
            latest_check = checks.last()
            
            return {
                'service_name': service_name,
                'uptime_percent': round(uptime_percent, 2),
                'total_checks': total_checks,
                'healthy_checks': healthy_checks,
                'hours': hours,
                'latest_status': latest_check.status,
                'latest_check_time': latest_check.checked_at.isoformat(),
            }
            
        except Exception as e:
            logger.error(f"خطا در محاسبه uptime: {str(e)}")
            return {'error': str(e)}
    
    def get_performance_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """دریافت متریک‌های عملکرد سیستم"""
        try:
            # متریک‌های فعلی سیستم
            current_metrics = {
                'cpu': self.check_cpu(),
                'memory': self.check_memory(),
                'disk': self.check_disk_space(),
            }
            
            # اگر محیط مشخص شده، متریک‌های سرویس‌ها را نیز اضافه کن
            if self.environment:
                from_time = timezone.now() - timezone.timedelta(hours=hours)
                
                # میانگین زمان پاسخ سرویس‌ها
                avg_response_times = HealthCheck.objects.filter(
                    environment=self.environment,
                    checked_at__gte=from_time,
                    response_time__isnull=False
                ).values('service_name').annotate(
                    avg_response_time=models.Avg('response_time'),
                    check_count=models.Count('id')
                )
                
                current_metrics['services_performance'] = list(avg_response_times)
            
            return {
                'timestamp': timezone.now().isoformat(),
                'period_hours': hours,
                'metrics': current_metrics,
            }
            
        except Exception as e:
            logger.error(f"خطا در دریافت متریک‌های عملکرد: {str(e)}")
            return {'error': str(e)}