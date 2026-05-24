"""
تست‌های اپلیکیشن DevOps
"""
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch, MagicMock
import json
from datetime import timedelta

from .models import (
    EnvironmentConfig,
    SecretConfig,
    DeploymentHistory,
    HealthCheck,
    ServiceMonitoring
)
from .services.docker_service import DockerService, DockerComposeService
from .services.deployment_service import DeploymentService
from .services.health_service import HealthService


class EnvironmentConfigTestCase(TestCase):
    """تست‌های مدل EnvironmentConfig"""
    
    def setUp(self):
        """راه‌اندازی اولیه تست‌ها"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
    def test_create_environment(self):
        """تست ایجاد محیط"""
        environment = EnvironmentConfig.objects.create(
            name='test_env',
            environment_type='development',
            description='محیط تست',
            created_by=self.user
        )
        
        self.assertEqual(environment.name, 'test_env')
        self.assertEqual(environment.environment_type, 'development')
        self.assertTrue(environment.is_active)
        self.assertEqual(str(environment), 'test_env (Development)')
    
    def test_environment_name_validation(self):
        """تست اعتبارسنجی نام محیط"""
        # نام معتبر
        env1 = EnvironmentConfig(
            name='valid-env_123',
            environment_type='production'
        )
        env1.full_clean()  # نباید خطا دهد
        
        # نام نامعتبر
        env2 = EnvironmentConfig(
            name='invalid env!',
            environment_type='production'
        )
        
        with self.assertRaises(Exception):
            env2.full_clean()


class SecretConfigTestCase(TestCase):
    """تست‌های مدل SecretConfig"""
    
    def setUp(self):
        """راه‌اندازی اولیه"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.environment = EnvironmentConfig.objects.create(
            name='test_env',
            environment_type='development',
            created_by=self.user
        )
    
    def test_create_secret(self):
        """تست ایجاد secret"""
        secret = SecretConfig.objects.create(
            environment=self.environment,
            key_name='TEST_SECRET',
            encrypted_value='encrypted_test_value',
            category='api_key',
            created_by=self.user
        )
        
        self.assertEqual(secret.key_name, 'TEST_SECRET')
        self.assertEqual(secret.category, 'api_key')
        self.assertFalse(secret.is_expired)
        self.assertEqual(str(secret), 'TEST_SECRET (test_env)')
    
    def test_secret_expiry(self):
        """تست انقضای secret"""
        # Secret منقضی شده
        expired_secret = SecretConfig.objects.create(
            environment=self.environment,
            key_name='EXPIRED_SECRET',
            encrypted_value='value',
            expires_at=timezone.now() - timedelta(days=1),
            created_by=self.user
        )
        
        self.assertTrue(expired_secret.is_expired)
        
        # Secret غیر منقضی شده
        valid_secret = SecretConfig.objects.create(
            environment=self.environment,
            key_name='VALID_SECRET',
            encrypted_value='value',
            expires_at=timezone.now() + timedelta(days=30),
            created_by=self.user
        )
        
        self.assertFalse(valid_secret.is_expired)


class DeploymentHistoryTestCase(TestCase):
    """تست‌های مدل DeploymentHistory"""
    
    def setUp(self):
        """راه‌اندازی اولیه"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.environment = EnvironmentConfig.objects.create(
            name='test_env',
            environment_type='development',
            created_by=self.user
        )
    
    def test_create_deployment(self):
        """تست ایجاد deployment"""
        deployment = DeploymentHistory.objects.create(
            environment=self.environment,
            version='v1.0.0',
            commit_hash='abc123def456',
            branch='main',
            deployed_by=self.user,
            status='success'
        )
        
        self.assertEqual(deployment.version, 'v1.0.0')
        self.assertEqual(deployment.status, 'success')
        self.assertEqual(str(deployment), 'test_env - v1.0.0 (موفق)')
    
    def test_deployment_duration(self):
        """تست محاسبه مدت زمان deployment"""
        start_time = timezone.now()
        end_time = start_time + timedelta(minutes=5)
        
        deployment = DeploymentHistory.objects.create(
            environment=self.environment,
            version='v1.0.0',
            started_at=start_time,
            completed_at=end_time,
            deployed_by=self.user
        )
        
        self.assertEqual(deployment.duration.total_seconds(), 300)  # 5 minutes


class HealthServiceTestCase(TestCase):
    """تست‌های سرویس Health Check"""
    
    def setUp(self):
        """راه‌اندازی اولیه"""
        self.environment = EnvironmentConfig.objects.create(
            name='test_env',
            environment_type='development'
        )
        
        self.health_service = HealthService('test_env')
    
    @patch('devops.services.health_service.connection')
    def test_check_database(self, mock_connection):
        """تست بررسی پایگاه داده"""
        # Mock successful database check
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.execute.return_value = None
        mock_cursor.fetchone.return_value = (1,)
        
        result = self.health_service.check_database()
        
        self.assertEqual(result['status'], 'healthy')
        self.assertIn('response_time', result)
        self.assertGreaterEqual(result['response_time'], 0)
    
    @patch('devops.services.health_service.cache')
    def test_check_cache(self, mock_cache):
        """تست بررسی کش"""
        # Mock successful cache check
        mock_cache.set.return_value = True
        mock_cache.get.return_value = 'OK'
        mock_cache.delete.return_value = True
        
        with patch('devops.services.health_service.get_redis_connection') as mock_redis:
            mock_redis_conn = MagicMock()
            mock_redis.return_value = mock_redis_conn
            mock_redis_conn.info.return_value = {
                'redis_version': '7.0',
                'used_memory_human': '10M',
                'connected_clients': 5,
                'uptime_in_seconds': 3600
            }
            
            result = self.health_service.check_cache()
            
            self.assertEqual(result['status'], 'healthy')
            self.assertIn('response_time', result)
            self.assertEqual(result['version'], '7.0')
    
    @patch('devops.services.health_service.psutil')
    def test_check_disk_space(self, mock_psutil):
        """تست بررسی فضای دیسک"""
        # Mock disk usage (70% used)
        mock_usage = MagicMock()
        mock_usage.total = 100 * 1024**3  # 100GB
        mock_usage.used = 70 * 1024**3   # 70GB
        mock_usage.free = 30 * 1024**3   # 30GB
        mock_psutil.disk_usage.return_value = mock_usage
        
        result = self.health_service.check_disk_space()
        
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['percent_used'], 70.0)
        self.assertEqual(result['total_gb'], 100.0)


class DockerServiceTestCase(TestCase):
    """تست‌های سرویس Docker"""
    
    @patch('devops.services.docker_service.docker')
    def test_docker_service_init(self, mock_docker):
        """تست اتصال به Docker"""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.ping.return_value = True
        
        docker_service = DockerService()
        
        self.assertIsNotNone(docker_service.client)
        mock_docker.from_env.assert_called_once()
        mock_client.ping.assert_called_once()
    
    @patch('devops.services.docker_service.docker')
    def test_get_container_status(self, mock_docker):
        """تست دریافت وضعیت container"""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.ping.return_value = True
        
        # Mock container
        mock_container = MagicMock()
        mock_container.name = 'test_container'
        mock_container.status = 'running'
        mock_container.image.tags = ['test:latest']
        mock_container.attrs = {'Created': '2023-01-01T00:00:00Z'}
        mock_container.ports = {'8000/tcp': [{'HostPort': '8000'}]}
        
        mock_client.containers.get.return_value = mock_container
        
        docker_service = DockerService()
        result = docker_service.get_container_status('test_container')
        
        self.assertEqual(result['name'], 'test_container')
        self.assertEqual(result['status'], 'running')
        self.assertEqual(result['image'], 'test:latest')


class HealthCheckAPITestCase(APITestCase):
    """تست‌های API Health Check"""
    
    def test_health_check_endpoint(self):
        """تست endpoint اصلی health check"""
        with patch('devops.views.HealthService') as mock_health_service:
            mock_health_service.return_value.comprehensive_health_check.return_value = {
                'overall_status': 'healthy',
                'timestamp': '2023-01-01T00:00:00Z',
                'services': {
                    'database': {'status': 'healthy'},
                    'cache': {'status': 'healthy'}
                }
            }
            
            url = reverse('devops:health_check')
            response = self.client.get(url)
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['overall_status'], 'healthy')
    
    def test_health_check_critical_status(self):
        """تست health check با وضعیت بحرانی"""
        with patch('devops.views.HealthService') as mock_health_service:
            mock_health_service.return_value.comprehensive_health_check.return_value = {
                'overall_status': 'critical',
                'timestamp': '2023-01-01T00:00:00Z',
                'services': {
                    'database': {'status': 'critical', 'error': 'Connection failed'}
                }
            }
            
            url = reverse('devops:health_check')
            response = self.client.get(url)
            
            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertEqual(response.data['overall_status'], 'critical')


class DeploymentAPITestCase(APITestCase):
    """تست‌های API Deployment"""
    
    def setUp(self):
        """راه‌اندازی اولیه"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.environment = EnvironmentConfig.objects.create(
            name='test_env',
            environment_type='development'
        )
        
        self.client.force_authenticate(user=self.user)
    
    @patch('devops.views.DeploymentService')
    def test_deployment_api(self, mock_deployment_service):
        """تست API deployment"""
        # Mock deployment
        mock_deployment = MagicMock()
        mock_deployment.id = 'test-deployment-id'
        mock_deployment.version = 'v1.0.0'
        mock_deployment.status = 'success'
        mock_deployment.environment = self.environment
        
        mock_deployment_service.return_value.deploy.return_value = mock_deployment
        
        url = reverse('devops:deploy')
        data = {
            'environment': 'test_env',
            'version': 'v1.0.0',
            'branch': 'main'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_deployment_service.assert_called_once_with('test_env')


class ManagementCommandTestCase(TransactionTestCase):
    """تست‌های Management Commands"""
    
    def setUp(self):
        """راه‌اندازی اولیه"""
        self.environment = EnvironmentConfig.objects.create(
            name='test_env',
            environment_type='development'
        )
    
    @patch('devops.management.commands.health_check.HealthService')
    def test_health_check_command(self, mock_health_service):
        """تست command health_check"""
        from django.core.management import call_command
        from io import StringIO
        
        mock_health_service.return_value.comprehensive_health_check.return_value = {
            'overall_status': 'healthy',
            'services': {
                'database': {'status': 'healthy'},
                'cache': {'status': 'healthy'}
            }
        }
        
        out = StringIO()
        call_command('health_check', stdout=out)
        
        output = out.getvalue()
        self.assertIn('بررسی سلامت کلی سیستم', output)
        self.assertIn('سالم', output)
    
    @patch('devops.management.commands.setup_environment.EnvironmentConfig')
    def test_setup_environment_command(self, mock_environment):
        """تست command setup_environment"""
        from django.core.management import call_command
        from io import StringIO
        
        mock_environment.objects.filter.return_value.first.return_value = None
        mock_env_instance = MagicMock()
        mock_env_instance.name = 'test_env'
        mock_environment.objects.create.return_value = mock_env_instance
        
        out = StringIO()
        call_command(
            'setup_environment', 
            '--environment', 'test_env',
            '--type', 'development',
            '--quick-setup',
            '--force',
            stdout=out
        )
        
        output = out.getvalue()
        self.assertIn('راه‌اندازی با موفقیت انجام شد', output)


class IntegrationTestCase(TransactionTestCase):
    """تست‌های یکپارچگی"""
    
    def setUp(self):
        """راه‌اندازی اولیه"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.environment = EnvironmentConfig.objects.create(
            name='integration_test',
            environment_type='testing'
        )
        
        self.service_monitoring = ServiceMonitoring.objects.create(
            environment=self.environment,
            service_name='test_service',
            service_type='web',
            health_check_url='http://localhost:8000/health/',
            check_interval=300,
            timeout=30
        )
    
    def test_complete_workflow(self):
        """تست workflow کامل: environment -> monitoring -> health check -> deployment"""
        
        # 1. بررسی ایجاد محیط
        self.assertTrue(self.environment.is_active)
        self.assertEqual(self.environment.name, 'integration_test')
        
        # 2. بررسی سرویس مانیتورینگ
        self.assertEqual(self.service_monitoring.service_name, 'test_service')
        self.assertTrue(self.service_monitoring.is_active)
        
        # 3. ایجاد health check (شبیه‌سازی)
        health_check = HealthCheck.objects.create(
            environment=self.environment,
            service_name='test_service',
            endpoint_url='http://localhost:8000/health/',
            status='healthy',
            response_time=150.5,
            status_code=200
        )
        
        self.assertEqual(health_check.status, 'healthy')
        self.assertLess(health_check.response_time, 1000)  # زیر 1 ثانیه
        
        # 4. ایجاد deployment
        deployment = DeploymentHistory.objects.create(
            environment=self.environment,
            version='v1.0.0-test',
            branch='test',
            deployed_by=self.user,
            status='success'
        )
        
        self.assertEqual(deployment.status, 'success')
        self.assertEqual(deployment.environment, self.environment)
        
        # 5. بررسی روابط
        self.assertEqual(self.environment.health_checks.count(), 1)
        self.assertEqual(self.environment.deployments.count(), 1)
        self.assertEqual(self.environment.monitored_services.count(), 1)