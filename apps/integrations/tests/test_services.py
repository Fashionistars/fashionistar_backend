"""
تست‌های سرویس‌های اپلیکیشن integrations
"""
from unittest.mock import patch, Mock, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from integrations.models import IntegrationProvider, IntegrationCredential
from integrations.services import (
    KavenegarService,
    AIIntegrationService,
    WebhookService
)

User = get_user_model()


class KavenegarServiceTest(TestCase):
    """تست سرویس Kavenegar"""
    
    def setUp(self):
        """آماده‌سازی داده‌های تست"""
        # ایجاد provider
        self.provider = IntegrationProvider.objects.create(
            name='Kavenegar',
            slug='kavenegar',
            provider_type='sms',
            status='active'
        )
        
        # ایجاد credentials
        IntegrationCredential.objects.create(
            provider=self.provider,
            key_name='api_key',
            key_value='test_api_key',
            environment='production'
        )
        
        IntegrationCredential.objects.create(
            provider=self.provider,
            key_name='sender_number',
            key_value='10004346',
            environment='production'
        )
        
        self.service = KavenegarService()
    
    @patch('integrations.services.kavenegar_service.requests.post')
    def test_send_otp_success(self, mock_post):
        """تست ارسال موفق OTP"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'return': {'status': 200, 'message': 'success'},
            'entries': [{'messageid': '123456', 'cost': 100}]
        }
        mock_post.return_value = mock_response
        
        # ارسال OTP
        result = self.service.send_otp(
            receptor='09123456789',
            token='12345'
        )
        
        # بررسی نتیجه
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], '123456')
        self.assertEqual(result['cost'], 100)
        
        # بررسی فراخوانی API
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn('verify/lookup.json', call_args[0][0])
    
    @patch('integrations.services.kavenegar_service.requests.post')
    def test_send_otp_failure(self, mock_post):
        """تست ارسال ناموفق OTP"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'return': {'status': 418, 'message': 'invalid receptor'},
            'entries': []
        }
        mock_post.return_value = mock_response
        
        # ارسال OTP
        result = self.service.send_otp(
            receptor='invalid',
            token='12345'
        )
        
        # بررسی نتیجه
        self.assertFalse(result['success'])
        self.assertIn('error', result)
    
    @patch('integrations.services.kavenegar_service.requests.post')
    def test_send_pattern(self, mock_post):
        """تست ارسال پیامک با قالب"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'return': {'status': 200, 'message': 'success'},
            'entries': [{'messageid': '789012', 'cost': 150}]
        }
        mock_post.return_value = mock_response
        
        # ارسال پیامک
        result = self.service.send_pattern(
            receptor='09123456789',
            template='appointment',
            tokens={'token': 'دکتر احمدی', 'token2': '1402/10/15'}
        )
        
        # بررسی نتیجه
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], '789012')
    
    @patch('integrations.services.kavenegar_service.cache')
    def test_rate_limiting(self, mock_cache):
        """تست محدودیت نرخ درخواست"""
        # تنظیم mock برای نشان دادن رسیدن به حد مجاز
        mock_cache.get.return_value = 10  # بیش از حد مجاز
        
        # ایجاد قانون rate limit
        from integrations.models import RateLimitRule
        RateLimitRule.objects.create(
            provider=self.provider,
            name='OTP Limit',
            endpoint_pattern='send_otp',
            max_requests=5,
            time_window_seconds=3600,
            scope='user',
            is_active=True
        )
        
        # تلاش برای ارسال
        result = self.service.send_otp(
            receptor='09123456789',
            token='12345'
        )
        
        # بررسی نتیجه
        self.assertFalse(result['success'])
        self.assertIn('بیش از حد مجاز', result['error'])


class AIIntegrationServiceTest(TestCase):
    """تست سرویس AI Integration"""
    
    def setUp(self):
        """آماده‌سازی داده‌های تست"""
        # ایجاد provider
        self.provider = IntegrationProvider.objects.create(
            name='OpenAI',
            slug='openai',
            provider_type='ai',
            status='active',
            api_base_url='https://api.openai.com/v1'
        )
        
        # ایجاد credential
        IntegrationCredential.objects.create(
            provider=self.provider,
            key_name='api_key',
            key_value='test_openai_key',
            environment='production'
        )
        
        self.service = AIIntegrationService('openai')
    
    @patch('integrations.services.ai_service.requests.post')
    def test_generate_text_success(self, mock_post):
        """تست تولید موفق متن"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {'content': 'This is a test response'},
                'finish_reason': 'stop'
            }],
            'usage': {'total_tokens': 50}
        }
        mock_post.return_value = mock_response
        
        # تولید متن
        result = self.service.generate_text(
            prompt='Hello, how are you?',
            max_tokens=100
        )
        
        # بررسی نتیجه
        self.assertTrue(result['success'])
        self.assertEqual(result['text'], 'This is a test response')
        self.assertEqual(result['usage']['total_tokens'], 50)
    
    @patch('integrations.services.ai_service.requests.post')
    def test_analyze_medical_text(self, mock_post):
        """تست تحلیل متن پزشکی"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {'content': 'تحلیل: بیمار علائم سرماخوردگی دارد'},
                'finish_reason': 'stop'
            }],
            'usage': {'total_tokens': 100}
        }
        mock_post.return_value = mock_response
        
        # تحلیل متن
        result = self.service.analyze_medical_text(
            text='سرفه و تب دارم',
            analysis_type='symptoms',
            patient_context={'age': 30, 'gender': 'male'}
        )
        
        # بررسی نتیجه
        self.assertTrue(result['success'])
        self.assertIn('تحلیل', result['text'])
    
    def test_get_default_base_url(self):
        """تست دریافت آدرس پایه پیش‌فرض"""
        # OpenAI
        url = self.service._get_default_base_url()
        self.assertEqual(url, 'https://api.openai.com/v1')
        
        # TalkBot
        talkbot_service = AIIntegrationService('talkbot')
        talkbot_service.provider_slug = 'talkbot'
        url = talkbot_service._get_default_base_url()
        self.assertEqual(url, 'https://api.talkbot.ir/v1')


class WebhookServiceTest(TestCase):
    """تست سرویس Webhook"""
    
    def setUp(self):
        """آماده‌سازی داده‌های تست"""
        # ایجاد provider
        self.provider = IntegrationProvider.objects.create(
            name='Webhook Provider',
            slug='webhook',
            provider_type='other',
            status='active'
        )
        
        self.service = WebhookService()
    
    def test_verify_signature_valid(self):
        """تست تأیید امضای معتبر"""
        secret_key = 'test_secret'
        payload = b'{"test": "data"}'
        
        # محاسبه امضای صحیح
        import hmac
        import hashlib
        correct_signature = hmac.new(
            secret_key.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        # تأیید امضا
        result = self.service.verify_signature(
            secret_key,
            payload,
            correct_signature
        )
        
        self.assertTrue(result)
    
    def test_verify_signature_invalid(self):
        """تست تأیید امضای نامعتبر"""
        secret_key = 'test_secret'
        payload = b'{"test": "data"}'
        wrong_signature = 'wrong_signature_123'
        
        # تأیید امضا
        result = self.service.verify_signature(
            secret_key,
            payload,
            wrong_signature
        )
        
        self.assertFalse(result)
    
    def test_register_webhook(self):
        """تست ثبت webhook جدید"""
        result = self.service.register_webhook(
            provider_slug='webhook',
            name='Test Webhook',
            endpoint_url='test-endpoint',
            events=['payment.success', 'payment.failed']
        )
        
        # بررسی نتیجه
        self.assertTrue(result['success'])
        self.assertIn('webhook_id', result)
        self.assertIn('secret_key', result)
        
        # بررسی ذخیره در دیتابیس
        from integrations.models import WebhookEndpoint
        webhook = WebhookEndpoint.objects.get(endpoint_url='test-endpoint')
        self.assertEqual(webhook.name, 'Test Webhook')
        self.assertEqual(webhook.events, ['payment.success', 'payment.failed'])
    
    def test_health_check(self):
        """تست بررسی سلامت سرویس"""
        # ایجاد webhook و رویداد
        from integrations.models import WebhookEndpoint, WebhookEvent
        
        webhook = WebhookEndpoint.objects.create(
            provider=self.provider,
            name='Test Webhook',
            endpoint_url='test-health',
            secret_key='secret123'
        )
        
        WebhookEvent.objects.create(
            webhook=webhook,
            event_type='test',
            payload={},
            is_processed=False
        )
        
        # بررسی سلامت
        result = self.service.health_check()
        
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['active_webhooks'], 1)
        self.assertEqual(result['pending_events'], 1)