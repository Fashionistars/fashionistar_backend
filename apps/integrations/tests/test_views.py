"""
Integrations ViewSet and API Tests for Fashionistar.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch
import json
import hmac
import hashlib

from ..models import (
    IntegrationProvider,
    IntegrationCredential,
    WebhookEndpoint,
    WebhookEvent
)

User = get_user_model()


class IntegrationProviderViewSetTest(TestCase):
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='testuser@fashionistar-test.io',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        self.provider = IntegrationProvider.objects.create(
            name='Test Provider',
            slug='test-provider',
            provider_type='sms',
            status='active'
        )
    
    def test_list_providers(self):
        url = reverse('integrations:provider-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'Test Provider')
    
    def test_retrieve_provider(self):
        url = reverse('integrations:provider-detail', kwargs={'slug': 'test-provider'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Provider')
        self.assertEqual(response.data['slug'], 'test-provider')
    
    def test_filter_by_type(self):
        IntegrationProvider.objects.create(
            name='AI Provider',
            slug='ai-provider',
            provider_type='ai',
            status='active'
        )
        
        url = reverse('integrations:provider-list')
        response = self.client.get(url, {'type': 'sms'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['provider_type'], 'sms')
    
    @patch('apps.integrations.services.sms_service.SMSService.health_check')
    def test_health_check_endpoint(self, mock_health_check):
        self.provider.slug = 'sms_provider'
        self.provider.save()
        
        mock_health_check.return_value = {
            'status': 'healthy',
            'response_time_ms': 100
        }
        
        url = reverse('integrations:provider-health-check', kwargs={'slug': 'sms_provider'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'healthy')


class SendSMSAPIViewTest(TestCase):
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='testuser@fashionistar-test.io',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        provider = IntegrationProvider.objects.create(
            name='SMS Provider',
            slug='sms_provider',
            provider_type='sms',
            status='active'
        )
        
        IntegrationCredential.objects.create(
            provider=provider,
            key_name='api_key',
            key_value='test_key',
            environment='production'
        )
    
    @patch('apps.integrations.services.sms_service.SMSService.send_otp')
    def test_send_otp(self, mock_send_otp):
        mock_send_otp.return_value = {
            'success': True,
            'message_id': '123456',
            'cost': 0.05
        }
        
        url = reverse('integrations:send-sms')
        data = {
            'receptor': '09123456789',
            'message_type': 'otp',
            'token': '12345'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message_id'], '123456')
    
    def test_send_sms_validation(self):
        url = reverse('integrations:send-sms')
        
        data = {
            'receptor': 'invalid_phone',
            'message_type': 'simple',
            'message': 'Test message'
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('receptor', response.data['errors'])
    
    def test_send_sms_unauthenticated(self):
        self.client.force_authenticate(user=None)
        
        url = reverse('integrations:send-sms')
        data = {
            'receptor': '09123456789',
            'message_type': 'simple',
            'message': 'Test'
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class WebhookReceiveAPIViewTest(TestCase):
    
    def setUp(self):
        self.client = APIClient()
        
        provider = IntegrationProvider.objects.create(
            name='Payment Gateway',
            slug='webhook',
            provider_type='payment',
            status='active'
        )
        
        self.webhook = WebhookEndpoint.objects.create(
            provider=provider,
            name='Payment Webhook',
            endpoint_url='payment-webhook',
            secret_key='test_secret_123',
            events=['payment.success', 'payment.failed']
        )
    
    def test_receive_webhook_success(self):
        url = reverse('integrations:webhook-receive', kwargs={'endpoint_url': 'payment-webhook'})
        
        payload = {
            'event': 'payment.success',
            'payment_id': '12345',
            'amount': 50000
        }
        
        raw_body = json.dumps(payload).encode()
        signature = hmac.new(
            self.webhook.secret_key.encode(),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        
        response = self.client.post(
            url,
            raw_body,
            content_type='application/json',
            HTTP_X_SIGNATURE=signature
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        event = WebhookEvent.objects.first()
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, 'payment.success')
        self.assertTrue(event.is_valid)
    
    def test_receive_webhook_invalid_signature(self):
        url = reverse('integrations:webhook-receive', kwargs={'endpoint_url': 'payment-webhook'})
        
        payload = {
            'event': 'payment.success',
            'payment_id': '12345'
        }
        
        response = self.client.post(
            url,
            payload,
            format='json',
            HTTP_X_SIGNATURE='wrong_signature'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['success'])
        
        event = WebhookEvent.objects.first()
        self.assertIsNotNone(event)
        self.assertFalse(event.is_valid)
    
    def test_receive_webhook_unknown_endpoint(self):
        url = reverse('integrations:webhook-receive', kwargs={'endpoint_url': 'unknown-endpoint'})
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['success'])
        self.assertIn('not found', response.data['error'])


class IntegrationCredentialViewSetTest(TestCase):
    
    def setUp(self):
        self.client = APIClient()
        
        self.admin_user = User.objects.create_superuser(
            password='admin123',
            email='admin@test.com'
        )
        self.client.force_authenticate(user=self.admin_user)
        
        self.provider = IntegrationProvider.objects.create(
            name='Test Provider',
            slug='test-provider',
            provider_type='sms'
        )
        
        self.credential = IntegrationCredential.objects.create(
            provider=self.provider,
            key_name='api_key',
            key_value='secret_key_123',
            environment='production',
            created_by=self.admin_user
        )
    
    def test_list_credentials_admin_only(self):
        normal_user = User.objects.create_user(
            email='normaluser@fashionistar-test.io',
            password='pass123'
        )
        self.client.force_authenticate(user=normal_user)
        
        url = reverse('integrations:credential-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_rotate_credential(self):
        url = reverse('integrations:credential-rotate', kwargs={'pk': str(self.credential.id)})
        
        data = {
            'new_value': 'new_secret_key_456'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        self.credential.refresh_from_db()
        self.assertEqual(self.credential.key_value, 'new_secret_key_456')
        
        from ..models import IntegrationLog
        log = IntegrationLog.objects.filter(action='rotate_credential').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.admin_user)