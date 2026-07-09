"""
Chatbot Tests for Fashionistar.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from unittest.mock import patch
from datetime import timedelta

from .models import ChatbotSession, Conversation, Message, ChatbotResponse
from .services import ClientChatbotService, VendorChatbotService, AIIntegrationService
from .serializers import (
    ChatbotSessionSerializer, MessageSerializer,
    SendMessageRequestSerializer
)

User = get_user_model()


class ChatbotModelsTest(TestCase):
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='user@fashionistar-test.io',
            first_name='Ahmed',
            last_name='Mohamadi',
            is_active=True
        )
    
    def test_chatbot_session_creation(self):
        session = ChatbotSession.objects.create(
            user=self.user,
            session_type='client',
            status='active'
        )
        
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.session_type, 'client')
        self.assertEqual(session.status, 'active')
        self.assertTrue(session.is_session_active)
        self.assertIsNotNone(session.id)
    
    def test_session_expiration(self):
        expired_session = ChatbotSession.objects.create(
            user=self.user,
            session_type='client',
            status='active',
            expires_at=timezone.now() - timedelta(hours=1)
        )
        self.assertFalse(expired_session.is_session_active)
    
    def test_conversation_creation(self):
        session = ChatbotSession.objects.create(
            user=self.user,
            session_type='client'
        )
        
        conversation = Conversation.objects.create(
            session=session,
            conversation_type='style_advice',
            title='Style Advice'
        )
        
        self.assertEqual(conversation.session, session)
        self.assertEqual(conversation.conversation_type, 'style_advice')
        self.assertEqual(conversation.message_count, 0)
    
    def test_message_creation(self):
        session = ChatbotSession.objects.create(
            user=self.user,
            session_type='client'
        )
        
        conversation = Conversation.objects.create(
            session=session,
            conversation_type='general'
        )
        
        message = Message.objects.create(
            conversation=conversation,
            sender_type='user',
            message_type='text',
            content='Hello, what is my style?'
        )
        
        self.assertEqual(message.conversation, conversation)
        self.assertTrue(message.is_from_user)
        self.assertFalse(message.is_from_bot)
        self.assertEqual(conversation.message_count, 1)
    
    def test_chatbot_response_model(self):
        response = ChatbotResponse.objects.create(
            category='greeting',
            target_user='client',
            trigger_keywords=['hello', 'hi'],
            response_text='Hello! How can I help you today?',
            priority=1
        )
        
        self.assertEqual(response.category, 'greeting')
        self.assertEqual(response.target_user, 'client')
        self.assertTrue(response.is_active)


class ChatbotServicesTest(TestCase):
    
    def setUp(self):
        self.client_user = User.objects.create_user(
            email='client@fashionistar-test.io',
            first_name='Ahmed',
            last_name='Mohamadi',
            role='client',
            is_active=True
        )
        
        self.vendor_user = User.objects.create_user(
            email='vendor@fashionistar-test.io',
            first_name='Vendor Jane',
            last_name='Doe',
            role='vendor',
            is_active=True
        )
        
        ChatbotResponse.objects.create(
            category='greeting',
            target_user='both',
            trigger_keywords=['hello', 'hi'],
            response_text='Hello! Welcome to Fashionistar.',
            priority=1
        )
    
    def test_client_chatbot_service(self):
        service = ClientChatbotService(self.client_user)
        
        session = service.get_or_create_session()
        self.assertEqual(session.user, self.client_user)
        self.assertEqual(session.session_type, 'client')
        
        conversation = service.get_or_create_conversation()
        self.assertEqual(conversation.session, session)
        
        user_message = service.save_user_message('hello')
        self.assertEqual(user_message.sender_type, 'user')
        self.assertEqual(user_message.content, 'hello')
    
    def test_vendor_chatbot_service(self):
        service = VendorChatbotService(self.vendor_user)
        
        session = service.get_or_create_session()
        self.assertEqual(session.session_type, 'vendor')
        
        result = service.process_message('sizing chart help')
        self.assertIn('response', result)
        self.assertIn('user_message_id', result)
        self.assertIn('bot_message_id', result)
    
    def test_ai_integration_service(self):
        ai_service = AIIntegrationService('client')
        response = ai_service.process_message('sizing help')
        
        self.assertIn('content', response)
        self.assertIn('ai_confidence', response)
        self.assertIn('processing_time', response)
        self.assertIsInstance(response['ai_confidence'], float)
    
    def test_style_assessment(self):
        service = ClientChatbotService(self.client_user)
        assessment = service.start_style_assessment()
        
        self.assertIn('content', assessment)
        self.assertIn('response_data', assessment)
        self.assertIn('assessment_questions', assessment['response_data'])
        
        responses = {
            'preferred_style': 'Streetwear',
            'budget_range': '$50-$150',
            'formality_level': 4
        }
        
        analysis = service.process_style_response(responses)
        self.assertIn('content', analysis)
        self.assertIn('response_data', analysis)


class ChatbotAPITest(APITestCase):
    
    def setUp(self):
        self.client_user = User.objects.create_user(
            email='client@fashionistar-test.io',
            first_name='Ahmed',
            last_name='Mohamadi',
            role='client',
            is_active=True
        )
        
        self.vendor_user = User.objects.create_user(
            email='vendor@fashionistar-test.io',
            first_name='Vendor Jane',
            last_name='Doe',
            role='vendor',
            is_active=True
        )
        
        self.client = APIClient()
    
    def test_client_start_session_api(self):
        self.client.force_authenticate(user=self.client_user)
        
        url = reverse('chatbot:client-start-session')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('session', response.data)
        self.assertIn('quick_replies', response.data)
    
    def test_client_send_message_api(self):
        self.client.force_authenticate(user=self.client_user)
        
        start_url = reverse('chatbot:client-start-session')
        self.client.post(start_url)
        
        send_url = reverse('chatbot:client-send-message')
        data = {
            'message': 'sizing help',
            'message_type': 'text'
        }
        
        response = self.client.post(send_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('response', response.data)
        self.assertIn('user_message_id', response.data)
        self.assertIn('bot_message_id', response.data)
    
    def test_vendor_catalog_support_api(self):
        self.client.force_authenticate(user=self.vendor_user)
        
        url = reverse('chatbot:vendor-catalog-support')
        data = {
            'measurements': ['Bust: 90cm', 'Waist: 70cm'],
            'height_cm': 175,
            'gender': 'F',
            'fit_preference': 'Regular'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('content', response.data)
        self.assertIn('response_data', response.data)
    
    def test_unauthorized_access(self):
        url = reverse('chatbot:client-start-session')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_invalid_message_data(self):
        self.client.force_authenticate(user=self.client_user)
        
        start_url = reverse('chatbot:client-start-session')
        self.client.post(start_url)
        
        send_url = reverse('chatbot:client-send-message')
        data = {'message': ''}
        
        response = self.client.post(send_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ChatbotSerializersTest(TestCase):
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='user@fashionistar-test.io',
            first_name='Ahmed',
            last_name='Mohamadi',
            is_active=True
        )
        
        self.session = ChatbotSession.objects.create(
            user=self.user,
            session_type='client'
        )
    
    def test_session_serializer(self):
        serializer = ChatbotSessionSerializer(self.session)
        data = serializer.data
        
        self.assertEqual(data['session_type'], 'client')
        self.assertIn('user', data)
        self.assertIn('conversation_count', data)
    
    def test_send_message_request_serializer(self):
        data = {
            'message': 'hello',
            'message_type': 'text'
        }
        
        serializer = SendMessageRequestSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        invalid_data = {'message': ''}
        invalid_serializer = SendMessageRequestSerializer(data=invalid_data)
        self.assertFalse(invalid_serializer.is_valid())
    
    def test_message_serializer_validation(self):
        conversation = Conversation.objects.create(
            session=self.session,
            conversation_type='general'
        )
        
        valid_data = {
            'conversation': conversation.id,
            'sender_type': 'user',
            'content': 'test message'
        }
        
        serializer = MessageSerializer(data=valid_data)
        self.assertTrue(serializer.is_valid())
        
        long_message = 'message ' * 1000
        invalid_data = {
            'conversation': conversation.id,
            'sender_type': 'user',
            'content': long_message
        }
        
        invalid_serializer = MessageSerializer(data=invalid_data)
        self.assertFalse(invalid_serializer.is_valid())


class ChatbotMiddlewareTest(TestCase):
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='user@fashionistar-test.io',
            first_name='Ahmed',
            last_name='Mohamadi',
            is_active=True
        )
        self.client = APIClient()
    
    @patch('django.core.cache.cache.get')
    @patch('django.core.cache.cache.set')
    def test_rate_limiting_middleware(self, mock_cache_set, mock_cache_get):
        mock_cache_get.return_value = [int(timezone.now().timestamp())] * 35
        
        self.client.force_authenticate(user=self.user)
        
        url = reverse('chatbot:client-send-message')
        data = {'message': 'test'}
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
    
    def test_security_middleware_sensitive_content(self):
        self.client.force_authenticate(user=self.user)
        
        start_url = reverse('chatbot:client-start-session')
        self.client.post(start_url)
        
        send_url = reverse('chatbot:client-send-message')
        sensitive_data = {
            'message': 'my credit card number is 1234'
        }
        
        response = self.client.post(send_url, sensitive_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Sensitive content', response.json()['error'])