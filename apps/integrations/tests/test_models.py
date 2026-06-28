"""
تست‌های مدل‌های اپلیکیشن integrations
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from integrations.models import (
    IntegrationProvider,
    IntegrationCredential,
    IntegrationLog,
    WebhookEndpoint,
    WebhookEvent,
    RateLimitRule
)

User = get_user_model()


class IntegrationProviderModelTest(TestCase):
    """تست مدل IntegrationProvider"""
    
    def setUp(self):
        """آماده‌سازی داده‌های تست"""
        self.provider = IntegrationProvider.objects.create(
            name='Kavenegar',
            slug='kavenegar',
            provider_type='sms',
            status='active',
            description='سرویس پیامک کاوه‌نگار',
            api_base_url='https://api.kavenegar.com/v1'
        )
    
    def test_provider_creation(self):
        """تست ایجاد provider"""
        self.assertTrue(isinstance(self.provider, IntegrationProvider))
        self.assertEqual(self.provider.name, 'Kavenegar')
        self.assertEqual(self.provider.slug, 'kavenegar')
        self.assertEqual(str(self.provider), 'Kavenegar (پیامک)')
    
    def test_provider_status_choices(self):
        """تست وضعیت‌های مختلف provider"""
        self.provider.status = 'inactive'
        self.provider.save()
        self.assertEqual(self.provider.status, 'inactive')
        
        self.provider.status = 'maintenance'
        self.provider.save()
        self.assertEqual(self.provider.status, 'maintenance')


class IntegrationCredentialModelTest(TestCase):
    """تست مدل IntegrationCredential"""
    
    def setUp(self):
        """آماده‌سازی داده‌های تست"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.provider = IntegrationProvider.objects.create(
            name='Test Provider',
            slug='test-provider',
            provider_type='sms'
        )
        
        self.credential = IntegrationCredential.objects.create(
            provider=self.provider,
            key_name='api_key',
            key_value='test_api_key_123',
            environment='production',
            created_by=self.user
        )
    
    def test_credential_creation(self):
        """تست ایجاد credential"""
        self.assertEqual(self.credential.key_name, 'api_key')
        self.assertEqual(self.credential.key_value, 'test_api_key_123')
        self.assertEqual(str(self.credential), 'Test Provider - api_key')
    
    def test_credential_validation(self):
        """تست اعتبارسنجی credential"""
        # credential فعال و بدون تاریخ انقضا
        self.assertTrue(self.credential.is_valid())
        
        # غیرفعال کردن
        self.credential.is_active = False
        self.credential.save()
        self.assertFalse(self.credential.is_valid())
        
        # فعال کردن و تنظیم تاریخ انقضا
        self.credential.is_active = True
        self.credential.expires_at = timezone.now() - timedelta(days=1)
        self.credential.save()
        self.assertFalse(self.credential.is_valid())
    
    def test_unique_constraint(self):
        """تست محدودیت یکتا بودن"""
        with self.assertRaises(Exception):
            IntegrationCredential.objects.create(
                provider=self.provider,
                key_name='api_key',
                key_value='another_value',
                environment='production',
                created_by=self.user
            )


class IntegrationLogModelTest(TestCase):
    """تست مدل IntegrationLog"""
    
    def setUp(self):
        """آماده‌سازی داده‌های تست"""
        self.provider = IntegrationProvider.objects.create(
            name='Test Provider',
            slug='test-provider',
            provider_type='sms'
        )
        
        self.log = IntegrationLog.objects.create(
            provider=self.provider,
            log_level='info',
            service_name='TestService',
            action='test_action',
            request_data={'test': 'data'},
            response_data={'result': 'success'},
            status_code=200,
            duration_ms=150
        )
    
    def test_log_creation(self):
        """تست ایجاد لاگ"""
        self.assertEqual(self.log.action, 'test_action')
        self.assertEqual(self.log.status_code, 200)
        self.assertEqual(self.log.duration_ms, 150)
        self.assertIn('Test Provider', str(self.log))
    
    def test_log_levels(self):
        """تست سطوح مختلف لاگ"""
        levels = ['debug', 'info', 'warning', 'error', 'critical']
        
        for level in levels:
            log = IntegrationLog.objects.create(
                provider=self.provider,
                log_level=level,
                service_name='TestService',
                action=f'test_{level}'
            )
            self.assertEqual(log.log_level, level)


class WebhookEndpointModelTest(TestCase):
    """تست مدل WebhookEndpoint"""
    
    def setUp(self):
        """آماده‌سازی داده‌های تست"""
        self.provider = IntegrationProvider.objects.create(
            name='Payment Gateway',
            slug='payment-gateway',
            provider_type='payment'
        )
        
        self.webhook = WebhookEndpoint.objects.create(
            provider=self.provider,
            name='Payment Status',
            endpoint_url='payment-status',
            secret_key='secret123',
            events=['payment.success', 'payment.failed']
        )
    
    def test_webhook_creation(self):
        """تست ایجاد webhook"""
        self.assertEqual(self.webhook.name, 'Payment Status')
        self.assertEqual(self.webhook.endpoint_url, 'payment-status')
        self.assertIn('payment.success', self.webhook.events)
        self.assertTrue(self.webhook.is_active)
    
    def test_webhook_unique_endpoint(self):
        """تست یکتا بودن endpoint"""
        with self.assertRaises(Exception):
            WebhookEndpoint.objects.create(
                provider=self.provider,
                name='Another Webhook',
                endpoint_url='payment-status',  # تکراری
                secret_key='another_secret'
            )


class WebhookEventModelTest(TestCase):
    """تست مدل WebhookEvent"""
    
    def setUp(self):
        """آماده‌سازی داده‌های تست"""
        self.provider = IntegrationProvider.objects.create(
            name='Test Provider',
            slug='test-provider',
            provider_type='payment'
        )
        
        self.webhook = WebhookEndpoint.objects.create(
            provider=self.provider,
            name='Test Webhook',
            endpoint_url='test-webhook',
            secret_key='secret123'
        )
        
        self.event = WebhookEvent.objects.create(
            webhook=self.webhook,
            event_type='test.event',
            payload={'test': 'data'},
            headers={'X-Test': 'header'},
            signature='test_signature',
            is_valid=True
        )
    
    def test_event_creation(self):
        """تست ایجاد رویداد"""
        self.assertEqual(self.event.event_type, 'test.event')
        self.assertEqual(self.event.payload['test'], 'data')
        self.assertTrue(self.event.is_valid)
        self.assertFalse(self.event.is_processed)
    
    def test_event_processing(self):
        """تست پردازش رویداد"""
        self.event.is_processed = True
        self.event.processed_at = timezone.now()
        self.event.save()
        
        self.assertTrue(self.event.is_processed)
        self.assertIsNotNone(self.event.processed_at)


class RateLimitRuleModelTest(TestCase):
    """تست مدل RateLimitRule"""
    
    def setUp(self):
        """آماده‌سازی داده‌های تست"""
        self.provider = IntegrationProvider.objects.create(
            name='Test Provider',
            slug='test-provider',
            provider_type='sms'
        )
        
        self.rule = RateLimitRule.objects.create(
            provider=self.provider,
            name='SMS Rate Limit',
            endpoint_pattern='/sms/send',
            max_requests=100,
            time_window_seconds=3600,
            scope='user'
        )
    
    def test_rule_creation(self):
        """تست ایجاد قانون"""
        self.assertEqual(self.rule.name, 'SMS Rate Limit')
        self.assertEqual(self.rule.max_requests, 100)
        self.assertEqual(self.rule.time_window_seconds, 3600)
        self.assertTrue(self.rule.is_active)
    
    def test_rule_string_representation(self):
        """تست نمایش رشته‌ای قانون"""
        expected = 'Test Provider - SMS Rate Limit (100/3600s)'
        self.assertEqual(str(self.rule), expected)