# apps/devops/services/health_service.py
"""
System Health Check and Monitoring Service.
"""
import requests
import time
import psutil
from typing import Dict, Optional, Any
from django.db import connection
from django.core.cache import cache
from django.utils import timezone
import logging

from ..models import HealthCheck, ServiceMonitoring, EnvironmentConfig

logger = logging.getLogger(__name__)


class HealthService:
    """System Health Check Service."""
    
    def __init__(self, environment_name: Optional[str] = None):
        """
        Set environment for health check.
        
        Args:
            environment_name: Name of the environment (optional)
        """
        self.environment = None
        if environment_name:
            try:
                self.environment = EnvironmentConfig.objects.get(
                    name=environment_name,
                    is_active=True
                )
            except EnvironmentConfig.DoesNotExist:
                logger.warning(f"Environment {environment_name} not found")
    
    def check_database(self) -> Dict[str, Any]:
        """Check database health."""
        start_time = time.time()
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            
            response_time = (time.time() - start_time) * 1000
            
            # Get additional database stats
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
            logger.error(f"Error checking database: {str(e)}")
            return {
                'status': 'critical',
                'error': str(e),
                'response_time': (time.time() - start_time) * 1000
            }
    
    def check_cache(self) -> Dict[str, Any]:
        """Check cache (Redis) health."""
        start_time = time.time()
        
        try:
            # Simple cache test
            test_key = f'health_check_{int(time.time())}'
            cache.set(test_key, 'OK', 10)
            value = cache.get(test_key)
            cache.delete(test_key)
            
            response_time = (time.time() - start_time) * 1000
            
            if value == 'OK':
                # Get Redis info
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
                    'error': 'Cache test failed',
                    'response_time': round(response_time, 2)
                }
                
        except Exception as e:
            logger.error(f"Error checking cache: {str(e)}")
            return {
                'status': 'critical',
                'error': str(e),
                'response_time': (time.time() - start_time) * 1000
            }
    
    def check_disk_space(self) -> Dict[str, Any]:
        """Check disk space usage."""
        try:
            disk_usage = psutil.disk_usage('/')
            total = disk_usage.total
            used = disk_usage.used
            free = disk_usage.free
            percent = (used / total) * 100
            
            # Determine status based on usage percentage
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
            logger.error(f"Error checking disk space: {str(e)}")
            return {
                'status': 'unknown',
                'error': str(e)
            }
    
    def check_memory(self) -> Dict[str, Any]:
        """Check system memory usage."""
        try:
            memory = psutil.virtual_memory()
            percent = memory.percent
            
            # Determine status based on usage percentage
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
            logger.error(f"Error checking memory: {str(e)}")
            return {
                'status': 'unknown',
                'error': str(e)
            }
    
    def check_cpu(self) -> Dict[str, Any]:
        """Check system CPU usage."""
        try:
            # Get CPU percent over 1 second
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
            
            # Determine status based on CPU load
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
            logger.error(f"Error checking CPU: {str(e)}")
            return {
                'status': 'unknown',
                'error': str(e)
            }
    
    def check_external_service(self, url: str, timeout: int = 10) -> Dict[str, Any]:
        """Check external service health."""
        start_time = time.time()
        
        try:
            response = requests.get(url, timeout=timeout)
            response_time = (time.time() - start_time) * 1000
            
            # Determine status based on response code and duration
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
            logger.error(f"Error checking service {url}: {str(e)}")
            return {
                'status': 'critical',
                'error': str(e),
                'response_time': (time.time() - start_time) * 1000,
                'url': url,
            }
    
    def comprehensive_health_check(self) -> Dict[str, Any]:
        """Comprehensive system health check."""
        start_time = time.time()
        
        results = {
            'timestamp': timezone.now().isoformat(),
            'overall_status': 'healthy',
            'services': {}
        }
        
        # Check database
        db_result = self.check_database()
        results['services']['database'] = db_result
        
        # Check cache
        cache_result = self.check_cache()
        results['services']['cache'] = cache_result
        
        # Check system resources
        results['services']['disk'] = self.check_disk_space()
        results['services']['memory'] = self.check_memory()
        results['services']['cpu'] = self.check_cpu()
        
        # Check monitored services
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
                
                # Save result to database
                self._save_health_check_result(service, service_result)
        
        # Determine overall status
        critical_count = sum(1 for s in results['services'].values() 
                           if s.get('status') == 'critical')
        warning_count = sum(1 for s in results['services'].values() 
                          if s.get('status') == 'warning')
        
        if critical_count > 0:
            results['overall_status'] = 'critical'
        elif warning_count > 0:
            results['overall_status'] = 'warning'
        
        # Total check duration
        results['total_check_time'] = round((time.time() - start_time) * 1000, 2)
        
        return results
    
    def _save_health_check_result(self, service: ServiceMonitoring, result: Dict[str, Any]):
        """Save health check result to database."""
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
            logger.error(f"Error saving health check result: {str(e)}")
    
    def get_service_uptime(self, service_name: str, hours: int = 24) -> Dict[str, Any]:
        """Calculate service uptime over specified hours."""
        if not self.environment:
            return {'error': 'Environment not specified'}
        
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
            
            # Latest status
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
            logger.error(f"Error calculating uptime: {str(e)}")
            return {'error': str(e)}
    
    def get_performance_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """Retrieve system performance metrics."""
        try:
            # Current system metrics
            current_metrics = {
                'cpu': self.check_cpu(),
                'memory': self.check_memory(),
                'disk': self.check_disk_space(),
            }
            
            # If environment is specified, append services performance metrics
            if self.environment:
                from_time = timezone.now() - timezone.timedelta(hours=hours)
                
                # Average response time of services
                from django.db.models import Avg, Count
                avg_response_times = HealthCheck.objects.filter(
                    environment=self.environment,
                    checked_at__gte=from_time,
                    response_time__isnull=False
                ).values('service_name').annotate(
                    avg_response_time=Avg('response_time'),
                    check_count=Count('id')
                )
                
                current_metrics['services_performance'] = list(avg_response_times)
            
            return {
                'timestamp': timezone.now().isoformat(),
                'period_hours': hours,
                'metrics': current_metrics,
            }
            
        except Exception as e:
            logger.error(f"Error retrieving performance metrics: {str(e)}")
            return {'error': str(e)}