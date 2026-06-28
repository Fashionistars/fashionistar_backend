"""
URL های سیستم چت‌بات
Chatbot URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PatientChatbotViewSet,
    DoctorChatbotViewSet,
    ChatbotSessionViewSet,
    ConversationViewSet,
    MessageViewSet
)

# ایجاد router برای ViewSet ها
router = DefaultRouter()
router.register(r'sessions', ChatbotSessionViewSet, basename='chatbot-session')
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'messages', MessageViewSet, basename='message')

app_name = 'chatbot'

urlpatterns = [
    # API عمومی چت‌بات
    path('api/', include(router.urls)),
    
    # API اختصاصی بیماران
    path('api/patient/start-session/', 
         PatientChatbotViewSet.as_view({'post': 'start_session'}), 
         name='patient-start-session'),
    
    path('api/patient/send-message/', 
         PatientChatbotViewSet.as_view({'post': 'send_message'}), 
         name='patient-send-message'),
    
    path('api/patient/symptom-assessment/', 
         PatientChatbotViewSet.as_view({'post': 'start_symptom_assessment'}), 
         name='patient-symptom-assessment'),
    
    path('api/patient/submit-assessment/', 
         PatientChatbotViewSet.as_view({'post': 'submit_symptom_assessment'}), 
         name='patient-submit-assessment'),
    
    path('api/patient/request-appointment/', 
         PatientChatbotViewSet.as_view({'post': 'request_appointment'}), 
         name='patient-request-appointment'),
    
    path('api/patient/end-session/', 
         PatientChatbotViewSet.as_view({'post': 'end_session'}), 
         name='patient-end-session'),
    
    # API اختصاصی پزشکان
    path('api/doctor/start-session/', 
         DoctorChatbotViewSet.as_view({'post': 'start_session'}), 
         name='doctor-start-session'),
    
    path('api/doctor/send-message/', 
         DoctorChatbotViewSet.as_view({'post': 'send_message'}), 
         name='doctor-send-message'),
    
    path('api/doctor/diagnosis-support/', 
         DoctorChatbotViewSet.as_view({'post': 'diagnosis_support'}), 
         name='doctor-diagnosis-support'),
    
    path('api/doctor/medication-info/', 
         DoctorChatbotViewSet.as_view({'post': 'medication_info'}), 
         name='doctor-medication-info'),
    
    path('api/doctor/treatment-protocol/', 
         DoctorChatbotViewSet.as_view({'get': 'treatment_protocol'}), 
         name='doctor-treatment-protocol'),
    
    path('api/doctor/search-references/', 
         DoctorChatbotViewSet.as_view({'get': 'search_references'}), 
         name='doctor-search-references'),
]