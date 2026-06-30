"""
Integration Services Tests for Fashionistar.
"""

from unittest.mock import patch, Mock
from django.test import TestCase
from django.contrib.auth import get_user_model
from ..models import IntegrationProvider, IntegrationCredential
from ..services import (
    SMSService,
    AIIntegrationService,
    WebhookService
)

User = get_user_model()


class SMSServiceTest(TestCase):
    
    def setUp(self):
        self.provider = IntegrationProvider.objects.create(
            name='SMS Provider',
            slug='sms_provider',
            provider_type='sms',
            status='active'
        )
        
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
        
        self.service = SMSService()
    
    def test_send_otp_success(self):
        result = self.service.send_otp(
            receptor='09123456789',
            token='12345'
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], 'msg-123')
        self.assertEqual(result['cost'], 0.05)
    
    def test_send_pattern(self):
        result = self.service.send_pattern(
            receptor='09123456789',
            template='style_advice',
            tokens={'token': 'Jane', 'token2': 'Streetwear'}
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], 'msg-pattern-123')
    
    @patch('django.core.cache.cache.get')
    def test_rate_limiting(self, mock_cache):
        mock_cache.return_value = 10
        
        from ..models import RateLimitRule
        RateLimitRule.objects.create(
            provider=self.provider,
            name='OTP Limit',
            endpoint_pattern='send_otp',
            max_requests=5,
            time_window_seconds=3600,
            scope='user',
            is_active=True
        )
        
        result = self.service.send_otp(
            receptor='09123456789',
            token='12345'
        )
        
        self.assertFalse(result['success'])
        self.assertIn('limit exceeded', result['error'].lower())


class AIIntegrationServiceTest(TestCase):
    
    def setUp(self):
        self.provider = IntegrationProvider.objects.create(
            name='OpenAI',
            slug='openai',
            provider_type='ai',
            status='active',
            api_base_url='https://api.openai.com/v1'
        )
        
        IntegrationCredential.objects.create(
            provider=self.provider,
            key_name='api_key',
            key_value='test_openai_key',
            environment='production'
        )
        
        self.service = AIIntegrationService('openai')
    
    @patch('requests.post')
    def test_generate_text_success(self, mock_post):
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
        
        result = self.service.generate_text(
            prompt='Hello, how are you?',
            max_tokens=100
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['text'], 'This is a test response')
        self.assertEqual(result['usage']['total_tokens'], 50)
    
    @patch('requests.post')
    def test_analyze_fashion_text(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {'content': 'Analysis: Client prefers Streetwear'},
                'finish_reason': 'stop'
            }],
            'usage': {'total_tokens': 100}
        }
        mock_post.return_value = mock_response
        
        result = self.service.analyze_fashion_text(
            text='Looking for streetwear styling ideas',
            analysis_type='styling',
            client_context={'size': 'M', 'height': '180cm'}
        )
        
        self.assertTrue(result['success'])
        self.assertIn('Analysis', result['text'])
    
    def test_get_default_base_url(self):
        url = self.service._get_default_base_url()
        self.assertEqual(url, 'https://api.openai.com/v1')
        
        talkbot_service = AIIntegrationService('talkbot')
        talkbot_service.provider_slug = 'talkbot'
        url = talkbot_service._get_default_base_url()
        self.assertEqual(url, 'https://api.talkbot.ir/v1')


class WebhookServiceTest(TestCase):
    
    def setUp(self):
        self.provider = IntegrationProvider.objects.create(
            name='Webhook Provider',
            slug='webhook',
            provider_type='other',
            status='active'
        )
        
        self.service = WebhookService()
    
    def test_verify_signature_valid(self):
        secret_key = 'test_secret'
        payload = b'{"test": "data"}'
        
        import hmac
        import hashlib
        correct_signature = hmac.new(
            secret_key.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        result = self.service.verify_signature(
            secret_key,
            payload,
            correct_signature
        )
        
        self.assertTrue(result)
    
    def test_verify_signature_invalid(self):
        secret_key = 'test_secret'
        payload = b'{"test": "data"}'
        wrong_signature = 'wrong_signature_123'
        
        result = self.service.verify_signature(
            secret_key,
            payload,
            wrong_signature
        )
        
        self.assertFalse(result)
    
    def test_register_webhook(self):
        result = self.service.register_webhook(
            provider_slug='webhook',
            name='Test Webhook',
            endpoint_url='test-endpoint',
            events=['payment.success', 'payment.failed']
        )
        
        self.assertTrue(result['success'])
        self.assertIn('webhook_id', result)
        self.assertIn('secret_key', result)
        
        from ..models import WebhookEndpoint
        webhook = WebhookEndpoint.objects.get(endpoint_url='test-endpoint')
        self.assertEqual(webhook.name, 'Test Webhook')
        self.assertEqual(webhook.events, ['payment.success', 'payment.failed'])
    
    def test_health_check(self):
        from ..models import WebhookEndpoint, WebhookEvent
        
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
        
        result = self.service.health_check()
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['active_webhooks'], 1)
        self.assertEqual(result['pending_events'], 1)