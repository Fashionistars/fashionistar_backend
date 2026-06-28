# apps/devops/services/docker_service.py
"""
Docker and Container Management Service.
"""
import docker
import subprocess
import json
from typing import Dict, List, Optional, Tuple, Any
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class DockerService:
    """Docker management service."""
    
    def __init__(self):
        """Connect to Docker daemon."""
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            logger.error(f"Error connecting to Docker: {str(e)}")
            raise ConnectionError("Unable to connect to Docker daemon")
    
    def get_container_status(self, container_name: str) -> Dict[str, Any]:
        """Get container status."""
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
            return {'error': f'Container {container_name} not found'}
        except Exception as e:
            logger.error(f"Error retrieving status of container {container_name}: {str(e)}")
            return {'error': str(e)}
    
    def get_all_containers(self) -> List[Dict[str, Any]]:
        """Get list of all containers."""
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
            logger.error(f"Error retrieving containers list: {str(e)}")
            return []
    
    def restart_container(self, container_name: str) -> Tuple[bool, str]:
        """Restart container."""
        try:
            container = self.client.containers.get(container_name)
            container.restart()
            logger.info(f"Container {container_name} restarted successfully")
            return True, f"Container {container_name} restarted successfully"
        except docker.errors.NotFound:
            return False, f"Container {container_name} not found"
        except Exception as e:
            logger.error(f"Error restarting {container_name}: {str(e)}")
            return False, str(e)
    
    def stop_container(self, container_name: str) -> Tuple[bool, str]:
        """Stop container."""
        try:
            container = self.client.containers.get(container_name)
            container.stop()
            logger.info(f"Container {container_name} stopped")
            return True, f"Container {container_name} stopped"
        except docker.errors.NotFound:
            return False, f"Container {container_name} not found"
        except Exception as e:
            logger.error(f"Error stopping {container_name}: {str(e)}")
            return False, str(e)
    
    def start_container(self, container_name: str) -> Tuple[bool, str]:
        """Start container."""
        try:
            container = self.client.containers.get(container_name)
            container.start()
            logger.info(f"Container {container_name} started")
            return True, f"Container {container_name} started"
        except docker.errors.NotFound:
            return False, f"Container {container_name} not found"
        except Exception as e:
            logger.error(f"Error starting {container_name}: {str(e)}")
            return False, str(e)
    
    def get_container_logs(self, container_name: str, lines: int = 100) -> str:
        """Get container logs."""
        try:
            container = self.client.containers.get(container_name)
            logs = container.logs(tail=lines).decode('utf-8')
            return logs
        except docker.errors.NotFound:
            return f"Container {container_name} not found"
        except Exception as e:
            logger.error(f"Error retrieving logs for {container_name}: {str(e)}")
            return f"Error retrieving logs: {str(e)}"
    
    def execute_command(self, container_name: str, command: str) -> Tuple[bool, str]:
        """Execute command inside container."""
        try:
            container = self.client.containers.get(container_name)
            result = container.exec_run(command)
            return result.exit_code == 0, result.output.decode('utf-8')
        except docker.errors.NotFound:
            return False, f"Container {container_name} not found"
        except Exception as e:
            logger.error(f"Error executing command in {container_name}: {str(e)}")
            return False, str(e)
    
    def _get_container_health(self, container) -> Dict[str, Any]:
        """Get container health status."""
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
        """Get container resource stats."""
        try:
            stats = container.stats(stream=False)
            
            # CPU usage calculation
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                           stats['precpu_stats']['system_cpu_usage']
            
            cpu_percent = 0.0
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * \
                             len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
            
            # Memory usage calculation
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
            logger.error(f"Error retrieving container stats: {str(e)}")
            return {}


class DockerComposeService:
    """Docker Compose management service."""
    
    def __init__(self, compose_file: str = 'docker-compose.yml'):
        """
        Set Docker Compose file path.
        
        Args:
            compose_file: Path to Docker Compose file
        """
        self.compose_file = compose_file
        self.project_dir = getattr(settings, 'BASE_DIR', '/app')
    
    def get_services_status(self) -> Dict[str, Any]:
        """Get status of all Docker Compose services."""
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
            logger.error(f"Error retrieving services status: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'services': []
            }
    
    def start_services(self, services: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Start Docker Compose services."""
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
                message = "Services started successfully"
                if services:
                    message = f"Services {', '.join(services)} started successfully"
                logger.info(message)
                return True, message
            else:
                logger.error(f"Error starting services: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout starting services"
        except Exception as e:
            logger.error(f"Error starting services: {str(e)}")
            return False, str(e)
    
    def stop_services(self, services: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Stop Docker Compose services."""
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
                message = "Services stopped"
                if services:
                    message = f"Services {', '.join(services)} stopped"
                logger.info(message)
                return True, message
            else:
                logger.error(f"Error stopping services: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout stopping services"
        except Exception as e:
            logger.error(f"Error stopping services: {str(e)}")
            return False, str(e)
    
    def restart_services(self, services: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Restart Docker Compose services."""
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
                message = "Services restarted"
                if services:
                    message = f"Services {', '.join(services)} restarted"
                logger.info(message)
                return True, message
            else:
                logger.error(f"Error restarting services: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout restarting services"
        except Exception as e:
            logger.error(f"Error restarting services: {str(e)}")
            return False, str(e)
    
    def get_service_logs(self, service_name: str, lines: int = 100) -> str:
        """Get Docker Compose service logs."""
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
                return f"Error retrieving logs: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return "Timeout retrieving logs"
        except Exception as e:
            logger.error(f"Error retrieving logs for service {service_name}: {str(e)}")
            return f"Error retrieving logs: {str(e)}"
    
    def build_services(self, services: Optional[List[str]] = None, no_cache: bool = False) -> Tuple[bool, str]:
        """Rebuild Docker Compose service images."""
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
                message = "Images built successfully"
                if services:
                    message = f"Images for {', '.join(services)} built successfully"
                logger.info(message)
                return True, message
            else:
                logger.error(f"Error building images: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout building images"
        except Exception as e:
            logger.error(f"Error building images: {str(e)}")
            return False, str(e)
    
    def pull_images(self, services: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Pull Docker Compose service images."""
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
                message = "Images pulled successfully"
                if services:
                    message = f"Images for {', '.join(services)} pulled successfully"
                logger.info(message)
                return True, message
            else:
                logger.error(f"Error pulling images: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout pulling images"
        except Exception as e:
            logger.error(f"Error pulling images: {str(e)}")
            return False, str(e)