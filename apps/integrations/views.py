"""
Integrations Views for Fashionistar.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta
import logging

from .models import (
    IntegrationProvider,
    IntegrationCredential,
    IntegrationLog,
    WebhookEndpoint,
    WebhookEvent,
    RateLimitRule
)
from .serializers import (
    IntegrationProviderSerializer,
    IntegrationCredentialSerializer,
    IntegrationLogSerializer,
    WebhookEndpointSerializer,
    WebhookEventSerializer,
    RateLimitRuleSerializer,
    SendSMSSerializer,
    AIGenerateSerializer
)
from .services import (
    SMSService,
    AIIntegrationService,
    WebhookService
)

logger = logging.getLogger(__name__)


class IntegrationProviderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing external Integration Providers.
    """
    queryset = IntegrationProvider.objects.all()
    serializer_class = IntegrationProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'slug'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        provider_type = self.request.query_params.get('type')
        if provider_type:
            queryset = queryset.filter(provider_type=provider_type)
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.annotate(
            credentials_count=Count('credentials'),
            webhooks_count=Count('webhooks')
        )
    
    @action(detail=True, methods=['get'])
    def health_check(self, request, slug=None):
        provider = self.get_object()
        
        try:
            if provider.slug == 'sms_provider':
                service = SMSService()
            elif provider.provider_type == 'ai':
                service = AIIntegrationService(provider.slug)
            else:
                return Response({
                    'error': 'Health check not implemented for this provider'
                }, status=status.HTTP_501_NOT_IMPLEMENTED)
            
            result = service.health_check()
            return Response(result)
            
        except Exception as e:
            logger.error(f"Health check failed for {provider.slug}: {str(e)}")
            return Response({
                'status': 'error',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, slug=None):
        provider = self.get_object()
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        
        logs = provider.logs.filter(created_at__gte=start_date)
        logs_stats = logs.values('log_level').annotate(count=Count('id'))
        
        webhook_stats = {}
        if provider.webhooks.exists():
            events = WebhookEvent.objects.filter(
                webhook__provider=provider,
                received_at__gte=start_date
            )
            webhook_stats = {
                'total': events.count(),
                'processed': events.filter(is_processed=True).count(),
                'failed': events.filter(is_processed=False, retry_count__gte=3).count()
            }
        
        return Response({
            'provider': provider.name,
            'period_days': days,
            'logs': {
                'total': logs.count(),
                'by_level': {item['log_level']: item['count'] for item in logs_stats}
            },
            'webhooks': webhook_stats,
            'credentials': {
                'total': provider.credentials.count(),
                'active': provider.credentials.filter(is_active=True).count()
            }
        })


class IntegrationCredentialViewSet(viewsets.ModelViewSet):
    queryset = IntegrationCredential.objects.all()
    serializer_class = IntegrationCredentialSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        provider_slug = self.request.query_params.get('provider')
        if provider_slug:
            queryset = queryset.filter(provider__slug=provider_slug)
        
        environment = self.request.query_params.get('environment')
        if environment:
            queryset = queryset.filter(environment=environment)
        
        if self.request.query_params.get('active_only') == 'true':
            queryset = queryset.filter(is_active=True)
        
        return queryset.select_related('provider', 'created_by')
    
    @action(detail=True, methods=['post'])
    def rotate(self, request, pk=None):
        credential = self.get_object()
        new_value = request.data.get('new_value')
        if not new_value:
            return Response({'error': 'new_value is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        IntegrationLog.objects.create(
            provider=credential.provider,
            log_level='info',
            service_name='CredentialRotation',
            action='rotate_credential',
            request_data={
                'credential_id': str(credential.id),
                'key_name': credential.key_name
            },
            user=request.user
        )
        
        credential.key_value = new_value
        credential.save()
        return Response({'success': True, 'message': 'Credential rotated successfully'})


class IntegrationLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IntegrationLog.objects.all()
    serializer_class = IntegrationLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        provider_slug = self.request.query_params.get('provider')
        if provider_slug:
            queryset = queryset.filter(provider__slug=provider_slug)
        
        log_level = self.request.query_params.get('level')
        if log_level:
            queryset = queryset.filter(log_level=log_level)
        
        days = self.request.query_params.get('days')
        if days:
            start_date = timezone.now() - timedelta(days=int(days))
            queryset = queryset.filter(created_at__gte=start_date)
        
        action_filter = self.request.query_params.get('action')
        if action_filter:
            queryset = queryset.filter(action__icontains=action_filter)
        
        return queryset.select_related('provider', 'user').order_by('-created_at')


class WebhookEndpointViewSet(viewsets.ModelViewSet):
    queryset = WebhookEndpoint.objects.all()
    serializer_class = WebhookEndpointSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        provider_slug = self.request.query_params.get('provider')
        if provider_slug:
            queryset = queryset.filter(provider__slug=provider_slug)
        
        if self.request.query_params.get('active_only') == 'true':
            queryset = queryset.filter(is_active=True)
        
        return queryset.select_related('provider').annotate(
            events_count=Count('events_received'),
            pending_count=Count('events_received', filter=Q(events_received__is_processed=False))
        )
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        webhook = self.get_object()
        
        test_event = WebhookEvent.objects.create(
            webhook=webhook,
            event_type='test',
            payload={
                'test': True,
                'timestamp': timezone.now().isoformat(),
                'message': 'This is a test event'
            },
            headers={'X-Test': 'true'},
            is_valid=True
        )
        
        service = WebhookService()
        result = service._process_event(webhook, test_event)
        
        if result['success']:
            test_event.is_processed = True
            test_event.processed_at = timezone.now()
        else:
            test_event.error_message = result.get('error', '')
        test_event.save()
        
        return Response({
            'success': result['success'],
            'event_id': str(test_event.id),
            'message': result.get('message', 'Test completed')
        })


class WebhookEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WebhookEvent.objects.all()
    serializer_class = WebhookEventSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        webhook_id = self.request.query_params.get('webhook')
        if webhook_id:
            queryset = queryset.filter(webhook_id=webhook_id)
        
        processed = self.request.query_params.get('processed')
        if processed is not None:
            queryset = queryset.filter(is_processed=processed.lower() == 'true')
        
        valid = self.request.query_params.get('valid')
        if valid is not None:
            queryset = queryset.filter(is_valid=valid.lower() == 'true')
        
        days = self.request.query_params.get('days')
        if days:
            start_date = timezone.now() - timedelta(days=int(days))
            queryset = queryset.filter(received_at__gte=start_date)
        
        return queryset.select_related('webhook', 'webhook__provider').order_by('-received_at')
    
    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        event = self.get_object()
        if event.is_processed:
            return Response({'error': 'Event already processed'}, status=status.HTTP_400_BAD_REQUEST)
        if not event.is_valid:
            return Response({'error': 'Cannot retry invalid event'}, status=status.HTTP_400_BAD_REQUEST)
        
        event.retry_count += 1
        event.save()
        
        service = WebhookService()
        result = service._process_event(event.webhook, event)
        
        if result['success']:
            event.is_processed = True
            event.processed_at = timezone.now()
        else:
            event.error_message = result.get('error', '')
        event.save()
        
        return Response({
            'success': result['success'],
            'message': result.get('message', 'Retry completed'),
            'retry_count': event.retry_count
        })


class RateLimitRuleViewSet(viewsets.ModelViewSet):
    queryset = RateLimitRule.objects.all()
    serializer_class = RateLimitRuleSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        provider_slug = self.request.query_params.get('provider')
        if provider_slug:
            queryset = queryset.filter(provider__slug=provider_slug)
        
        if self.request.query_params.get('active_only') == 'true':
            queryset = queryset.filter(is_active=True)
        
        return queryset.select_related('provider')


class SendSMSAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = SendSMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        service = SMSService()
        
        try:
            if data['message_type'] == 'otp':
                result = service.send_otp(
                    receptor=data['receptor'],
                    token=data['token'],
                    template=data.get('template')
                )
            elif data['message_type'] == 'pattern':
                result = service.send_pattern(
                    receptor=data['receptor'],
                    template=data['template'],
                    tokens=data['tokens']
                )
            else:
                result = service.send_bulk(
                    receptors=[data['receptor']],
                    message=data['message']
                )
            
            if result['success']:
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"SMS sending error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AIGenerateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = AIGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        provider_slug = request.query_params.get('provider', 'openai')
        service = AIIntegrationService(provider_slug)
        
        try:
            if data.get('analysis_type') and data['analysis_type'] != 'general':
                result = service.analyze_fashion_text(
                    text=data['prompt'],
                    analysis_type=data['analysis_type'],
                    client_context=data.get('client_context')
                )
            else:
                result = service.generate_text(
                    prompt=data['prompt'],
                    model=data.get('model'),
                    max_tokens=data['max_tokens'],
                    temperature=data['temperature'],
                    system_prompt=data.get('system_prompt')
                )
            
            if result['success']:
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"AI generation error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WebhookReceiveAPIView(APIView):
    permission_classes = []
    authentication_classes = []
    
    def post(self, request, endpoint_url):
        raw_body = request.body
        service = WebhookService()
        
        try:
            result = service.process_webhook(
                endpoint_url=endpoint_url,
                headers=dict(request.headers),
                payload=request.data,
                raw_body=raw_body
            )
            
            if result['success']:
                return Response({'success': True, 'message': 'Webhook received successfully'}, status=status.HTTP_200_OK)
            else:
                return Response({'success': False, 'error': result.get('error', 'Processing failed')}, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            return Response({'success': False, 'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)