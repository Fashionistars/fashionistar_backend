"""
URL patterns برای اپلیکیشن integrations
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from integrations.views import (
    IntegrationProviderViewSet,
    IntegrationCredentialViewSet,
    IntegrationLogViewSet,
    WebhookEndpointViewSet,
    WebhookEventViewSet,
    RateLimitRuleViewSet,
    SendSMSAPIView,
    AIGenerateAPIView,
    WebhookReceiveAPIView
)

app_name = 'integrations'

# Router setup
router = DefaultRouter()
router.register(r'providers', IntegrationProviderViewSet, basename='provider')
router.register(r'credentials', IntegrationCredentialViewSet, basename='credential')
router.register(r'logs', IntegrationLogViewSet, basename='log')
router.register(r'webhooks', WebhookEndpointViewSet, basename='webhook')
router.register(r'webhook-events', WebhookEventViewSet, basename='webhook-event')
router.register(r'rate-limits', RateLimitRuleViewSet, basename='rate-limit')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),
    
    # Custom API endpoints
    path('sms/send/', SendSMSAPIView.as_view(), name='send-sms'),
    path('ai/generate/', AIGenerateAPIView.as_view(), name='ai-generate'),
    
    # Webhook receiver (dynamic endpoint)
    path('webhook/<str:endpoint_url>/', WebhookReceiveAPIView.as_view(), name='webhook-receive'),
]