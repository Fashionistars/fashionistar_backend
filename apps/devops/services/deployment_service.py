# apps/devops/services/deployment_service.py
"""
CI/CD and Deployment Management Service.
"""
import subprocess
import git
from typing import List, Optional, Tuple
from django.conf import settings
from django.utils import timezone
import logging

from ..models import DeploymentHistory, EnvironmentConfig
from .docker_service import DockerComposeService

logger = logging.getLogger(__name__)


class DeploymentService:
    """Deployment management service."""
    
    def __init__(self, environment_name: str):
        """
        Configure deployment environment.
        
        Args:
            environment_name: Environment name (development, staging, production)
        """
        try:
            self.environment = EnvironmentConfig.objects.get(
                name=environment_name,
                is_active=True
            )
        except EnvironmentConfig.DoesNotExist:
            raise ValueError(f"Environment {environment_name} not found or is inactive")
        
        self.project_dir = getattr(settings, 'BASE_DIR', '/app')
        self.compose_service = DockerComposeService()
        
        # Set compose file based on environment
        if environment_name == 'production':
            self.compose_service.compose_file = 'docker-compose.prod.yml'
        elif environment_name == 'staging':
            self.compose_service.compose_file = 'docker-compose.staging.yml'
        else:
            self.compose_service.compose_file = 'docker-compose.yml'
    
    def deploy(
        self,
        version: str,
        branch: str = 'main',
        user=None,
        build_images: bool = True,
        run_migrations: bool = True,
        restart_services: bool = True
    ) -> DeploymentHistory:
        """
        Execute full deployment.
        
        Args:
            version: Version for deployment
            branch: Git branch name
            user: Triggering user
            build_images: Build images?
            run_migrations: Run migrations?
            restart_services: Restart services?
            
        Returns:
            DeploymentHistory: Deployment execution record
        """
        
        # Create deployment record
        deployment = DeploymentHistory.objects.create(
            environment=self.environment,
            version=version,
            branch=branch,
            deployed_by=user,
            status='pending'
        )
        
        logs = []
        
        try:
            deployment.status = 'running'
            deployment.save()
            
            logs.append(f"[{timezone.now()}] Starting deployment of version {version}")
            
            # 1. Pull latest code
            commit_hash = self._pull_latest_code(branch)
            deployment.commit_hash = commit_hash
            deployment.save()
            logs.append(f"[{timezone.now()}] Code updated - Commit: {commit_hash}")
            
            # 2. Build images (optional)
            if build_images:
                success, message = self._build_images()
                logs.append(f"[{timezone.now()}] Build Images: {message}")
                if not success:
                    raise Exception(f"Error building images: {message}")
            
            # 3. Run migrations (optional)
            if run_migrations:
                success, message = self._run_migrations()
                logs.append(f"[{timezone.now()}] Migrations: {message}")
                if not success:
                    raise Exception(f"Error executing migrations: {message}")
            
            # 4. Collect static files
            success, message = self._collect_static()
            logs.append(f"[{timezone.now()}] Collect Static: {message}")
            if not success:
                raise Exception(f"Error collecting static files: {message}")
            
            # 5. Restart services (optional)
            if restart_services:
                success, message = self._restart_services()
                logs.append(f"[{timezone.now()}] Restart Services: {message}")
                if not success:
                    raise Exception(f"Error restarting services: {message}")
            
            # 6. Check service health
            health_check_result = self._health_check()
            logs.append(f"[{timezone.now()}] Health Check: {health_check_result}")
            
            # Mark complete
            deployment.status = 'success'
            deployment.completed_at = timezone.now()
            logs.append(f"[{timezone.now()}] Deployment completed successfully")
            
        except Exception as e:
            # Mark failed
            deployment.status = 'failed'
            deployment.completed_at = timezone.now()
            logs.append(f"[{timezone.now()}] Error during deployment: {str(e)}")
            logger.error(f"Error during deployment: {str(e)}")
        
        finally:
            deployment.deployment_logs = '\n'.join(logs)
            deployment.save()
        
        return deployment
    
    def rollback(self, target_deployment_id: str, user=None) -> DeploymentHistory:
        """
        Rollback to a previous successful deployment.
        
        Args:
            target_deployment_id: ID of the target deployment
            user: Triggering user
            
        Returns:
            DeploymentHistory: Rollback execution record
        """
        try:
            target_deployment = DeploymentHistory.objects.get(
                id=target_deployment_id,
                environment=self.environment,
                status='success'
            )
        except DeploymentHistory.DoesNotExist:
            raise ValueError("Target deployment not found or was not successful")
        
        # Create rollback record
        rollback_deployment = DeploymentHistory.objects.create(
            environment=self.environment,
            version=f"rollback-{target_deployment.version}",
            branch=target_deployment.branch,
            commit_hash=target_deployment.commit_hash,
            deployed_by=user,
            status='pending',
            rollback_from=target_deployment
        )
        
        logs = []
        
        try:
            rollback_deployment.status = 'running'
            rollback_deployment.save()
            
            logs.append(f"[{timezone.now()}] Starting rollback to version {target_deployment.version}")
            
            # Checkout target commit
            success, message = self._checkout_commit(target_deployment.commit_hash)
            logs.append(f"[{timezone.now()}] Checkout Commit: {message}")
            if not success:
                raise Exception(f"Error during checkout: {message}")
            
            # Rebuild images
            success, message = self._build_images()
            logs.append(f"[{timezone.now()}] Build Images: {message}")
            if not success:
                raise Exception(f"Error building images: {message}")
            
            # Restart services
            success, message = self._restart_services()
            logs.append(f"[{timezone.now()}] Restart Services: {message}")
            if not success:
                raise Exception(f"Error during restart: {message}")
            
            # Check service health
            health_check_result = self._health_check()
            logs.append(f"[{timezone.now()}] Health Check: {health_check_result}")
            
            # Mark complete
            rollback_deployment.status = 'success'
            rollback_deployment.completed_at = timezone.now()
            logs.append(f"[{timezone.now()}] Rollback completed successfully")
            
        except Exception as e:
            rollback_deployment.status = 'failed'
            rollback_deployment.completed_at = timezone.now()
            logs.append(f"[{timezone.now()}] Error during rollback: {str(e)}")
            logger.error(f"Error during rollback: {str(e)}")
        
        finally:
            rollback_deployment.deployment_logs = '\n'.join(logs)
            rollback_deployment.save()
        
        return rollback_deployment
    
    def _pull_latest_code(self, branch: str) -> str:
        """Pull latest code from git."""
        try:
            repo = git.Repo(self.project_dir)
            
            # Fetch latest changes
            repo.remotes.origin.fetch()
            
            # Checkout to branch
            repo.git.checkout(branch)
            
            # Pull latest changes
            repo.remotes.origin.pull()
            
            # Get current commit hash
            commit_hash = repo.head.commit.hexsha
            
            logger.info(f"Code updated - Branch: {branch}, Commit: {commit_hash}")
            return commit_hash
            
        except Exception as e:
            logger.error(f"Error pulling code: {str(e)}")
            raise Exception(f"Error retrieving code: {str(e)}")
    
    def _checkout_commit(self, commit_hash: str) -> Tuple[bool, str]:
        """Checkout to specific commit."""
        try:
            repo = git.Repo(self.project_dir)
            repo.git.checkout(commit_hash)
            
            logger.info(f"Checkout to commit {commit_hash} completed")
            return True, f"Checkout to commit {commit_hash} successful"
            
        except Exception as e:
            logger.error(f"Error during checkout to commit {commit_hash}: {str(e)}")
            return False, str(e)
    
    def _build_images(self) -> Tuple[bool, str]:
        """Build Docker images."""
        try:
            return self.compose_service.build_services(no_cache=False)
        except Exception as e:
            logger.error(f"Error building images: {str(e)}")
            return False, str(e)
    
    def _run_migrations(self) -> Tuple[bool, str]:
        """Run Django migrations in Docker container."""
        try:
            result = subprocess.run(
                ['docker-compose', '-f', self.compose_service.compose_file, 
                 'exec', '-T', 'web', 'python', 'manage.py', 'migrate', '--noinput'],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes
            )
            
            if result.returncode == 0:
                logger.info("Migrations completed successfully")
                return True, "Migrations completed successfully"
            else:
                logger.error(f"Error executing migrations: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout executing migrations"
        except Exception as e:
            logger.error(f"Error executing migrations: {str(e)}")
            return False, str(e)
    
    def _collect_static(self) -> Tuple[bool, str]:
        """Collect static files in Docker container."""
        try:
            result = subprocess.run(
                ['docker-compose', '-f', self.compose_service.compose_file,
                 'exec', '-T', 'web', 'python', 'manage.py', 'collectstatic', '--noinput'],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=180  # 3 minutes
            )
            
            if result.returncode == 0:
                logger.info("Static files collected successfully")
                return True, "Static files collected successfully"
            else:
                logger.error(f"Error collecting static files: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout collecting static files"
        except Exception as e:
            logger.error(f"Error collecting static files: {str(e)}")
            return False, str(e)
    
    def _restart_services(self) -> Tuple[bool, str]:
        """Restart Docker services."""
        try:
            return self.compose_service.restart_services()
        except Exception as e:
            logger.error(f"Error restarting services: {str(e)}")
            return False, str(e)
    
    def _health_check(self) -> str:
        """Check service health after deployment."""
        try:
            services_status = self.compose_service.get_services_status()
            
            if services_status['success']:
                running_count = services_status['running_services']
                total_count = services_status['total_services']
                
                if running_count == total_count:
                    return f"All services ({total_count}) are healthy"
                else:
                    return f"Only {running_count} out of {total_count} services are running"
            else:
                return f"Health check error: {services_status.get('error', 'unknown')}"
                
        except Exception as e:
            logger.error(f"Error during health check: {str(e)}")
            return f"Health check error: {str(e)}"
    
    def get_deployment_history(self, limit: int = 10) -> List[DeploymentHistory]:
        """Retrieve deployment history."""
        return DeploymentHistory.objects.filter(
            environment=self.environment
        ).order_by('-started_at')[:limit]
    
    def get_latest_successful_deployment(self) -> Optional[DeploymentHistory]:
        """Retrieve latest successful deployment."""
        return DeploymentHistory.objects.filter(
            environment=self.environment,
            status='success'
        ).order_by('-completed_at').first()
    
    def cancel_deployment(self, deployment_id: str) -> Tuple[bool, str]:
        """Cancel running deployment execution."""
        try:
            deployment = DeploymentHistory.objects.get(
                id=deployment_id,
                environment=self.environment,
                status__in=['pending', 'running']
            )
            
            deployment.status = 'cancelled'
            deployment.completed_at = timezone.now()
            deployment.deployment_logs += f"\n[{timezone.now()}] Deployment cancelled"
            deployment.save()
            
            logger.info(f"Deployment {deployment_id} cancelled")
            return True, f"Deployment {deployment_id} cancelled"
            
        except DeploymentHistory.DoesNotExist:
            return False, "Deployment not found or is not cancellable"
        except Exception as e:
            logger.error(f"Error cancelling deployment: {str(e)}")
            return False, str(e)