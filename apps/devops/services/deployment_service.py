"""
سرویس مدیریت deployment و CI/CD
"""
import subprocess
import os
import git
import time
import json
from typing import Dict, List, Optional, Tuple, Any
from django.conf import settings
from django.utils import timezone
from datetime import datetime
import logging

from ..models import DeploymentHistory, EnvironmentConfig
from .docker_service import DockerComposeService

logger = logging.getLogger(__name__)


class DeploymentService:
    """سرویس مدیریت deployment"""
    
    def __init__(self, environment_name: str):
        """
        تنظیم محیط deployment
        
        Args:
            environment_name: نام محیط (development, staging, production)
        """
        try:
            self.environment = EnvironmentConfig.objects.get(
                name=environment_name,
                is_active=True
            )
        except EnvironmentConfig.DoesNotExist:
            raise ValueError(f"محیط {environment_name} یافت نشد یا غیرفعال است")
        
        self.project_dir = getattr(settings, 'BASE_DIR', '/app')
        self.compose_service = DockerComposeService()
        
        # تنظیم compose file بر اساس محیط
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
        اجرای deployment کامل
        
        Args:
            version: نسخه برای deployment
            branch: شاخه git
            user: کاربر اجراکننده
            build_images: آیا image ها ساخته شوند
            run_migrations: آیا migration ها اجرا شوند
            restart_services: آیا سرویس‌ها راه‌اندازی مجدد شوند
            
        Returns:
            DeploymentHistory: رکورد تاریخچه deployment
        """
        
        # ایجاد رکورد deployment
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
            
            logs.append(f"[{timezone.now()}] شروع deployment نسخه {version}")
            
            # 1. دریافت آخرین کد
            commit_hash = self._pull_latest_code(branch)
            deployment.commit_hash = commit_hash
            deployment.save()
            logs.append(f"[{timezone.now()}] کد آپدیت شد - Commit: {commit_hash}")
            
            # 2. ساخت image ها (اختیاری)
            if build_images:
                success, message = self._build_images()
                logs.append(f"[{timezone.now()}] Build Images: {message}")
                if not success:
                    raise Exception(f"خطا در ساخت image ها: {message}")
            
            # 3. اجرای migration ها (اختیاری)
            if run_migrations:
                success, message = self._run_migrations()
                logs.append(f"[{timezone.now()}] Migrations: {message}")
                if not success:
                    raise Exception(f"خطا در اجرای migration ها: {message}")
            
            # 4. جمع‌آوری فایل‌های static
            success, message = self._collect_static()
            logs.append(f"[{timezone.now()}] Collect Static: {message}")
            if not success:
                raise Exception(f"خطا در جمع‌آوری static files: {message}")
            
            # 5. راه‌اندازی مجدد سرویس‌ها (اختیاری)
            if restart_services:
                success, message = self._restart_services()
                logs.append(f"[{timezone.now()}] Restart Services: {message}")
                if not success:
                    raise Exception(f"خطا در راه‌اندازی مجدد سرویس‌ها: {message}")
            
            # 6. بررسی سلامت سرویس‌ها
            health_check_result = self._health_check()
            logs.append(f"[{timezone.now()}] Health Check: {health_check_result}")
            
            # تکمیل موفق
            deployment.status = 'success'
            deployment.completed_at = timezone.now()
            logs.append(f"[{timezone.now()}] Deployment با موفقیت تکمیل شد")
            
        except Exception as e:
            # خطا در deployment
            deployment.status = 'failed'
            deployment.completed_at = timezone.now()
            logs.append(f"[{timezone.now()}] خطا در deployment: {str(e)}")
            logger.error(f"خطا در deployment: {str(e)}")
        
        finally:
            deployment.deployment_logs = '\n'.join(logs)
            deployment.save()
        
        return deployment
    
    def rollback(self, target_deployment_id: str, user=None) -> DeploymentHistory:
        """
        بازگشت به deployment قبلی
        
        Args:
            target_deployment_id: ID deployment مقصد
            user: کاربر اجراکننده
            
        Returns:
            DeploymentHistory: رکورد rollback
        """
        try:
            target_deployment = DeploymentHistory.objects.get(
                id=target_deployment_id,
                environment=self.environment,
                status='success'
            )
        except DeploymentHistory.DoesNotExist:
            raise ValueError("Deployment مقصد یافت نشد یا موفق نبوده")
        
        # ایجاد رکورد rollback
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
            
            logs.append(f"[{timezone.now()}] شروع rollback به نسخه {target_deployment.version}")
            
            # بازگشت به commit مورد نظر
            success, message = self._checkout_commit(target_deployment.commit_hash)
            logs.append(f"[{timezone.now()}] Checkout Commit: {message}")
            if not success:
                raise Exception(f"خطا در checkout: {message}")
            
            # ساخت مجدد image ها
            success, message = self._build_images()
            logs.append(f"[{timezone.now()}] Build Images: {message}")
            if not success:
                raise Exception(f"خطا در ساخت image ها: {message}")
            
            # راه‌اندازی مجدد سرویس‌ها
            success, message = self._restart_services()
            logs.append(f"[{timezone.now()}] Restart Services: {message}")
            if not success:
                raise Exception(f"خطا در راه‌اندازی مجدد: {message}")
            
            # بررسی سلامت
            health_check_result = self._health_check()
            logs.append(f"[{timezone.now()}] Health Check: {health_check_result}")
            
            # تکمیل موفق
            rollback_deployment.status = 'success'
            rollback_deployment.completed_at = timezone.now()
            logs.append(f"[{timezone.now()}] Rollback با موفقیت تکمیل شد")
            
        except Exception as e:
            rollback_deployment.status = 'failed'
            rollback_deployment.completed_at = timezone.now()
            logs.append(f"[{timezone.now()}] خطا در rollback: {str(e)}")
            logger.error(f"خطا در rollback: {str(e)}")
        
        finally:
            rollback_deployment.deployment_logs = '\n'.join(logs)
            rollback_deployment.save()
        
        return rollback_deployment
    
    def _pull_latest_code(self, branch: str) -> str:
        """دریافت آخرین کد از git"""
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
            
            logger.info(f"کد آپدیت شد - Branch: {branch}, Commit: {commit_hash}")
            return commit_hash
            
        except Exception as e:
            logger.error(f"خطا در pull کردن کد: {str(e)}")
            raise Exception(f"خطا در دریافت کد: {str(e)}")
    
    def _checkout_commit(self, commit_hash: str) -> Tuple[bool, str]:
        """رفتن به commit خاص"""
        try:
            repo = git.Repo(self.project_dir)
            repo.git.checkout(commit_hash)
            
            logger.info(f"Checkout به commit {commit_hash} انجام شد")
            return True, f"Checkout به commit {commit_hash} موفق بود"
            
        except Exception as e:
            logger.error(f"خطا در checkout به commit {commit_hash}: {str(e)}")
            return False, str(e)
    
    def _build_images(self) -> Tuple[bool, str]:
        """ساخت Docker images"""
        try:
            return self.compose_service.build_services(no_cache=False)
        except Exception as e:
            logger.error(f"خطا در ساخت images: {str(e)}")
            return False, str(e)
    
    def _run_migrations(self) -> Tuple[bool, str]:
        """اجرای Django migrations"""
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
                logger.info("Migration ها با موفقیت اجرا شدند")
                return True, "Migration ها با موفقیت اجرا شدند"
            else:
                logger.error(f"خطا در اجرای migration ها: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout در اجرای migration ها"
        except Exception as e:
            logger.error(f"خطا در اجرای migration ها: {str(e)}")
            return False, str(e)
    
    def _collect_static(self) -> Tuple[bool, str]:
        """جمع‌آوری static files"""
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
                logger.info("Static files با موفقیت جمع‌آوری شدند")
                return True, "Static files با موفقیت جمع‌آوری شدند"
            else:
                logger.error(f"خطا در جمع‌آوری static files: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Timeout در جمع‌آوری static files"
        except Exception as e:
            logger.error(f"خطا در جمع‌آوری static files: {str(e)}")
            return False, str(e)
    
    def _restart_services(self) -> Tuple[bool, str]:
        """راه‌اندازی مجدد سرویس‌ها"""
        try:
            return self.compose_service.restart_services()
        except Exception as e:
            logger.error(f"خطا در راه‌اندازی مجدد سرویس‌ها: {str(e)}")
            return False, str(e)
    
    def _health_check(self) -> str:
        """بررسی سلامت سرویس‌ها پس از deployment"""
        try:
            services_status = self.compose_service.get_services_status()
            
            if services_status['success']:
                running_count = services_status['running_services']
                total_count = services_status['total_services']
                
                if running_count == total_count:
                    return f"تمام سرویس‌ها ({total_count}) سالم هستند"
                else:
                    return f"تنها {running_count} از {total_count} سرویس در حال اجرا هستند"
            else:
                return f"خطا در بررسی سلامت: {services_status.get('error', 'نامشخص')}"
                
        except Exception as e:
            logger.error(f"خطا در health check: {str(e)}")
            return f"خطا در بررسی سلامت: {str(e)}"
    
    def get_deployment_history(self, limit: int = 10) -> List[DeploymentHistory]:
        """دریافت تاریخچه deployment ها"""
        return DeploymentHistory.objects.filter(
            environment=self.environment
        ).order_by('-started_at')[:limit]
    
    def get_latest_successful_deployment(self) -> Optional[DeploymentHistory]:
        """دریافت آخرین deployment موفق"""
        return DeploymentHistory.objects.filter(
            environment=self.environment,
            status='success'
        ).order_by('-completed_at').first()
    
    def cancel_deployment(self, deployment_id: str) -> Tuple[bool, str]:
        """لغو deployment در حال اجرا"""
        try:
            deployment = DeploymentHistory.objects.get(
                id=deployment_id,
                environment=self.environment,
                status__in=['pending', 'running']
            )
            
            deployment.status = 'cancelled'
            deployment.completed_at = timezone.now()
            deployment.deployment_logs += f"\n[{timezone.now()}] Deployment لغو شد"
            deployment.save()
            
            logger.info(f"Deployment {deployment_id} لغو شد")
            return True, f"Deployment {deployment_id} لغو شد"
            
        except DeploymentHistory.DoesNotExist:
            return False, "Deployment یافت نشد یا قابل لغو نیست"
        except Exception as e:
            logger.error(f"خطا در لغو deployment: {str(e)}")
            return False, str(e)