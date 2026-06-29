"""
Chatbot URLs for Fashionistar.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClientChatbotViewSet,
    VendorChatbotViewSet,
    ChatbotSessionViewSet,
    ConversationViewSet,
    MessageViewSet
)

router = DefaultRouter()
router.register(r'sessions', ChatbotSessionViewSet, basename='chatbot-session')
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'messages', MessageViewSet, basename='message')

app_name = 'chatbot'

urlpatterns = [
    path('api/', include(router.urls)),
    
    # Client Endpoints
    path('api/client/start-session/', 
         ClientChatbotViewSet.as_view({'post': 'start_session'}), 
         name='client-start-session'),
    
    path('api/client/send-message/', 
         ClientChatbotViewSet.as_view({'post': 'send_message'}), 
         name='client-send-message'),
    
    path('api/client/style-assessment/', 
         ClientChatbotViewSet.as_view({'post': 'start_style_assessment'}), 
         name='client-style-assessment'),
    
    path('api/client/submit-assessment/', 
         ClientChatbotViewSet.as_view({'post': 'submit_style_assessment'}), 
         name='client-submit-assessment'),
    
    path('api/client/request-consultation/', 
         ClientChatbotViewSet.as_view({'post': 'request_appointment'}), 
         name='client-request-consultation'),
    
    path('api/client/end-session/', 
         ClientChatbotViewSet.as_view({'post': 'end_session'}), 
         name='client-end-session'),
    
    # Vendor Endpoints
    path('api/vendor/start-session/', 
         VendorChatbotViewSet.as_view({'post': 'start_session'}), 
         name='vendor-start-session'),
    
    path('api/vendor/send-message/', 
         VendorChatbotViewSet.as_view({'post': 'send_message'}), 
         name='vendor-send-message'),
    
    path('api/vendor/catalog-support/', 
         VendorChatbotViewSet.as_view({'post': 'diagnosis_support'}), 
         name='vendor-catalog-support'),
    
    path('api/vendor/product-info/', 
         VendorChatbotViewSet.as_view({'post': 'medication_info'}), 
         name='vendor-product-info'),
    
    path('api/vendor/tailoring-guideline/', 
         VendorChatbotViewSet.as_view({'get': 'treatment_protocol'}), 
         name='vendor-tailoring-guideline'),
    
    path('api/vendor/search-references/', 
         VendorChatbotViewSet.as_view({'get': 'search_references'}), 
         name='vendor-search-references'),
]