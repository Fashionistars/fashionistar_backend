"""
سرویس مدیریت Docker و container ها
"""
import docker
import subprocess
import os
import json
import time
from typing import Dict, List, Optional, Tuple, Any
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class DockerService:
    """سرویس مدیریت Docker"""
    
    def __init__(self):
        """اتصال به Docker daemon"""
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            logger.error(f"خطا در اتصال به Docker: {str(e)}")
            raise ConnectionError("امکان اتصال به Docker وجود ندارد")
    
    def get_container_status(self, container_name: str) -> Dict[str, Any]:
        """دریافت وضعیت container"""
        try:
            container = self.client.containers.get(container_name)
            return {
                'name': container.name,
                'status': container.status,
                'image': container.image.tags[0] if container.image.tags else 'unknown',
                'created': container.attrs['Created'],
                'ports': container.ports,
                'health': self._get_container_health(container),
                'stats': self._get_container_stats(container),
            }
        except docker.errors.NotFound:
            return {'error': f'Container {container_name} یافت نشد'}
        except Exception as e:
            logger.error(f"خطا در دریافت وضعیت container {container_name}: {str(e)}")
            return {'error': str(e)}
    
    def get_all_containers(self) -> List[Dict[str, Any]]:
        """دریافت لیست تمام container ها"""
        try:
            containers = []
            for container in self.client.containers.list(all=True):
                containers.append({
                    'name': container.name,
                    'id': container.short_id,
                    'status': container.status,
                    'image': container.image.tags[0] if container.image.tags else 'unknown',
                    'created': container.attrs['Created'],
                    'ports': container.ports,
                })
            return containers
        except Exception as e:
            logger.error(f"خطا در دریافت لیست container ها: {str(e)}")
            return []
    
    def restart_container(self, container_name: str) -> Tuple[bool, str]:
        """راه‌اندازی مجدد container"""
        try:
            container = self.client.containers.get(container_name)
            container.restart()
            logger.info(f"Container {container_name} با موفقیت راه‌اندازی مجدد شد")
            return True, f"Container {container_name} با موفقیت راه‌اندازی مجدد شد"
        except docker.errors.NotFound:
            return False, f"Container {container_name} یافت نشد"
        except Exception as e:
            logger.error(f"خطا در راه‌اندازی مجدد {container_name}: {str(e)}")
            return False, str(e)
    
    def stop_container(self, container_name: str) -> Tuple[bool, str]:
        """توقف container"""
        try:
            container = self.client.containers.get(container_name)
            container.stop()
            logger.info(f"Container {container_name} متوقف شد")
            return True, f"Container {container_name} متوقف شد"
        except docker.errors.NotFound:
            return False, f"Container {container_name} یافت نشد"
        except Exception as e:
            logger.error(f"خطا در توقف {container_name}: {str(e)}")
            return False, str(e)
    
    def start_container(self, container_name: str) -> Tuple[bool, str]:
        """شروع container"""
        try:
            container = self.client.containers.get(container_name)
            container.start()
            logger.info(f"Container {container_name} شروع شد")
            return True, f"Container {container_name} شروع شد"
        except docker.errors.NotFound:
            return False, f"Container {container_name} یافت نشد"
        except Exception as e:
            logger.error(f"خطا در شروع {container_name}: {str(e)}")
            return False, str(e)
    
    def get_container_logs(self, container_name: str, lines: int = 100) -> str:
        """دریافت لاگ‌های container"""
        try:
            container = self.client.containers.get(container_name)
            logs = container.logs(tail=lines).decode('utf-8')
            return logs
        except docker.errors.NotFound:
            return f"Container {container_name} یافت نشد"
        except Exception as e:
            logger.error(f"خطا در دریافت لاگ‌های {container_name}: {str(e)}")
            return f"خطا در دریافت لاگ‌ها: {str(e)}"
    
    def execute_command(self, container_name: str, command: str) -> Tuple[bool, str]:
        """اجرای دستور در container"""
        try:
            container = self.client.containers.get(container_name)
            result = container.exec_run(command)
            return result.exit_code == 0, result.output.decode('utf-8')
        except docker.errors.NotFound:
            return False, f"Container {container_name} یافت نشد"
        except Exception as e:
            logger.error(f"خطا در اجرای دستور در {container_name}: {str(e)}")
            return False, str(e)
    
    def _get_container_health(self, container) -> Dict[str, Any]:
        """دریافت وضعیت سلامت container"""
        try:
            health = container.attrs.get('State', {}).get('Health', {})
            if health:
                return {
                    'status': health.get('Status', 'unknown'),
                    'failing_streak': health.get('FailingStreak', 0),
                    'log': health.get('Log', [])[-1] if health.get('Log') else {}
                }
            return {'status': 'no_healthcheck'}
        except Exception:
            return {'status': 'unknown'}
    
    def _get_container_stats(self, container) -> Dict[str, Any]:
        """دریافت آمار container"""
        try:
            stats = container.stats(stream=False)
            
            # محاسبه CPU usage
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            
            cpu_percent = 0.0
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * \
                             len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
            
            # محاسبه Memory usage
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            memory_percent = (memory_usage / memory_limit) * 100.0
            
            return {
                'cpu_percent': round(cpu_percent, 2),
                'memory_usage': memory_usage,
                'memory_limit': memory_limit,
                'memory_percent': round(memory_percent, 2),
                'network_rx': stats['networks'].get('eth0', {}).get('rx_bytes', 0),
                'network_tx': stats['networks'].get('eth0', {}).get('tx_bytes', 0),
            }
        except Exception as e:
            logger.error(f"خطا در دریافت آمار container: {str(e)}")
            return {}


class DockerComposeService:
    """سرویس مدیریت Docker Compose"""
    
    def __init__(self, compose_file: str = 'docker-compose.yml'):
        """
        تنظیم مسیر فایل docker-compose
        
        Args:
            compose_file: مسیر فایل docker-compose
        """
        self.compose_file = compose_file
        self.project_dir = getattr(settings, 'BASE_DIR', '/app')
    
    def get_services_status(self) -> Dict[str, Any]:
        """دریافت وضعیت تمام سرویس‌های compose"""
        try:
            result = subprocess.run(
                ['docker-compose', '-f', self.compose_file, 'ps', '--format', 'json'],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Parse JSON output
                services = []
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        services.append(json.loads(line))
                
                return {
                    'success': True,
                    'services': services,
                    'total_services': len(services),
                    'running_services': len([s for s in services if s.get('State') == 'running'])
                }
            else:
                return {
                    'success': False,
                    'error': result.stderr,
                    'services': []
                }
        except Exception as e:
            logger.error(f"خطا در دریافت وضعیت سرویس‌ها: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'services': []
            }
    
    def start_services(self, services: Optional[List[str]] = None) -> Tuple[bool, str]:
        """شروع سرویس‌های compose"""
        try:
            cmd = ['docker-compose', '-f', self.compose_file, 'up', '-d']
            if services:
                cmd.extend(services)
            
            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes
            )
            
            if result.returncode == 0:
                message = f"سرویس‌ها با موفقیت شروع شدند"
                if services:
                    message = f"سرویس‌های {', '.join(services)} با موفقیت شروع شدند"
                logger.info(message)
                return True, message
            else:
                logger.error(f"خطا در شروع سرویس‌ها: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout در شروع سرویس‌ها"
        except Exception as e:
            logger.error(f"خطا در شروع سرویس‌ها: {str(e)}")
            return False, str(e)
    
    def stop_services(self, services: Optional[List[str]] = None) -> Tuple[bool, str]:
        """توقف سرویس‌های compose"""
        try:
            cmd = ['docker-compose', '-f', self.compose_file, 'stop']
            if services:
                cmd.extend(services)
            
            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=120  # 2 minutes
            )
            
            if result.returncode == 0:
                message = f"سرویس‌ها متوقف شدند"
                if services:
                    message = f"سرویس‌های {', '.join(services)} متوقف شدند"
                logger.info(message)
                return True, message
            else:
                logger.error(f"خطا در توقف سرویس‌ها: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout در توقف سرویس‌ها"
        except Exception as e:
            logger.error(f"خطا در توقف سرویس‌ها: {str(e)}")
            return False, str(e)
    
    def restart_services(self, services: Optional[List[str]] = None) -> Tuple[bool, str]:
        """راه‌اندازی مجدد سرویس‌های compose"""
        try:
            cmd = ['docker-compose', '-f', self.compose_file, 'restart']
            if services:
                cmd.extend(services)
            
            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=180  # 3 minutes
            )
            
            if result.returncode == 0:
                message = f"سرویس‌ها راه‌اندازی مجدد شدند"
                if services:
                    message = f"سرویس‌های {', '.join(services)} راه‌اندازی مجدد شدند"
                logger.info(message)
                return True, message
            else:
                logger.error(f"خطا در راه‌اندازی مجدد سرویس‌ها: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout در راه‌اندازی مجدد سرویس‌ها"
        except Exception as e:
            logger.error(f"خطا در راه‌اندازی مجدد سرویس‌ها: {str(e)}")
            return False, str(e)
    
    def get_service_logs(self, service_name: str, lines: int = 100) -> str:
        """دریافت لاگ‌های سرویس"""
        try:
            result = subprocess.run(
                ['docker-compose', '-f', self.compose_file, 'logs', '--tail', str(lines), service_name],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                return f"خطا در دریافت لاگ‌ها: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return "Timeout در دریافت لاگ‌ها"
        except Exception as e:
            logger.error(f"خطا در دریافت لاگ‌های سرویس {service_name}: {str(e)}")
            return f"خطا در دریافت لاگ‌ها: {str(e)}"
    
    def build_services(self, services: Optional[List[str]] = None, no_cache: bool = False) -> Tuple[bool, str]:
        """ساخت مجدد image های سرویس‌ها"""
        try:
            cmd = ['docker-compose', '-f', self.compose_file, 'build']
            if no_cache:
                cmd.append('--no-cache')
            if services:
                cmd.extend(services)
            
            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes
            )
            
            if result.returncode == 0:
                message = f"Image ها با موفقیت ساخته شدند"
                if services:
                    message = f"Image های {', '.join(services)} با موفقیت ساخته شدند"
                logger.info(message)
                return True, message
            else:
                logger.error(f"خطا در ساخت image ها: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout در ساخت image ها"
        except Exception as e:
            logger.error(f"خطا در ساخت image ها: {str(e)}")
            return False, str(e)
    
    def pull_images(self, services: Optional[List[str]] = None) -> Tuple[bool, str]:
        """دانلود آخرین image ها"""
        try:
            cmd = ['docker-compose', '-f', self.compose_file, 'pull']
            if services:
                cmd.extend(services)
            
            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes
            )
            
            if result.returncode == 0:
                message = f"Image ها با موفقیت دانلود شدند"
                if services:
                    message = f"Image های {', '.join(services)} با موفقیت دانلود شدند"
                logger.info(message)
                return True, message
            else:
                logger.error(f"خطا در دانلود image ها: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout در دانلود image ها"
        except Exception as e:
            logger.error(f"خطا در دانلود image ها: {str(e)}")
            return False, str(e)