"""
الگوهای استاندارد API Views
Standard API View Patterns
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.throttling import UserRateThrottle
from rest_framework.pagination import PageNumberPagination
from django.db import transaction
from django.core.cache import cache
from app_standards.permissions import IsPatient, IsDoctor
from app_standards.four_cores import APIIngressCore, CentralOrchestrator
import logging
from django.http import JsonResponse

logger = logging.getLogger(__name__)


# Pagination Classes
class StandardPagination(PageNumberPagination):
    """صفحه‌بندی استاندارد"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# Throttle Classes
class StandardUserThrottle(UserRateThrottle):
    """محدودیت نرخ برای کاربران احراز هویت شده"""
    rate = '100/hour'


class AIRequestThrottle(UserRateThrottle):
    """محدودیت نرخ برای درخواست‌های AI"""
    rate = '20/hour'
    
    
# Base API Views
class BaseAPIView(APIView):
    """
    کلاس پایه برای API Views
    شامل error handling و logging استاندارد
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [StandardUserThrottle]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ingress = APIIngressCore()
        self.orchestrator = CentralOrchestrator()
        
    def handle_exception(self, exc):
        """مدیریت استثناءها"""
        logger.error(f"API Exception: {str(exc)}", exc_info=True)
        return super().handle_exception(exc)


# Function-based Views
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([StandardUserThrottle])
def standard_api_endpoint(request):
    """
    الگوی استاندارد برای function-based views
    """
    ingress = APIIngressCore()
    
    try:
        if request.method == 'GET':
            # دریافت داده‌ها
            data = {'message': 'Success', 'user': request.user.username}
            return Response(data, status=status.HTTP_200_OK)
            
        elif request.method == 'POST':
            # اعتبارسنجی
            from app.serializers import ExampleSerializer
            is_valid, validated_data = ingress.validate_request(
                request.data,
                ExampleSerializer
            )
            
            if not is_valid:
                return Response(
                    ingress.build_error_response('validation', validated_data),
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # پردازش
            result = process_data(validated_data, request.user)
            
            return Response(result, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        logger.error(f"Error in endpoint: {str(e)}")
        return Response(
            ingress.build_error_response('internal'),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Class-based Views
class PatientChatView(BaseAPIView):
    """
    نمونه View برای چت بیمار
    """
    permission_classes = [IsAuthenticated, IsPatient]
    throttle_classes = [StandardUserThrottle, AIRequestThrottle]
    
    def post(self, request):
        """ارسال پیام چت"""
        try:
            # اعتبارسنجی
            from patient_chatbot.serializers import ChatMessageSerializer
            is_valid, data = self.ingress.validate_request(
                request.data,
                ChatMessageSerializer
            )
            
            if not is_valid:
                return Response(
                    self.ingress.build_error_response('validation', data),
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # اجرای workflow
            result = self.orchestrator.execute_workflow(
                'medical_chat',
                data,
                request.user
            )
            
            if result.status == 'completed':
                return Response(
                    result.data,
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'error': 'Processing failed', 'details': result.errors},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Exception as e:
            logger.exception("Chat processing error")
            return Response(
                self.ingress.build_error_response('internal'),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DoctorDashboardView(BaseAPIView):
    """
    داشبورد پزشک
    """
    permission_classes = [IsAuthenticated, IsDoctor]
    
    def get(self, request):
        """دریافت اطلاعات داشبورد"""
        try:
            # بررسی cache
            cache_key = f"doctor_dashboard:{request.user.id}"
            cached_data = cache.get(cache_key)
            
            if cached_data:
                return Response(cached_data)
            
            # جمع‌آوری داده‌ها
            dashboard_data = {
                'today_visits': self._get_today_visits(request.user),
                'pending_reports': self._get_pending_reports(request.user),
                'patient_messages': self._get_patient_messages(request.user),
                'statistics': self._get_statistics(request.user),
            }
            
            # ذخیره در cache
            cache.set(cache_key, dashboard_data, 300)  # 5 minutes
            
            return Response(dashboard_data)
            
        except Exception as e:
            logger.error(f"Dashboard error: {str(e)}")
            return Response(
                self.ingress.build_error_response('internal'),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_today_visits(self, doctor):
        """دریافت ویزیت‌های امروز"""
        # Implementation
        return []
    
    def _get_pending_reports(self, doctor):
        """دریافت گزارش‌های در انتظار"""
        # Implementation
        return []
    
    def _get_patient_messages(self, doctor):
        """دریافت پیام‌های بیماران"""
        # Implementation
        return []
    
    def _get_statistics(self, doctor):
        """دریافت آمار"""
        # Implementation
        return {}


# Generic Views
class PatientListView(ListAPIView):
    """
    لیست بیماران برای پزشک
    """
    permission_classes = [IsAuthenticated, IsDoctor]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        """دریافت queryset بر اساس پزشک"""
        from patient_records.models import PatientRecord
        return PatientRecord.objects.filter(
            doctor=self.request.user,
            is_active=True
        ).select_related('patient')
    
    def get_serializer_class(self):
        """انتخاب serializer"""
        from patient_records.serializers import PatientListSerializer
        return PatientListSerializer


# ViewSets
class PrescriptionViewSet(ModelViewSet):
    """
    ViewSet برای مدیریت نسخه‌ها
    """
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    
    def get_permissions(self):
        """تعیین دسترسی‌ها بر اساس action"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAuthenticated, IsDoctor]
        return super().get_permissions()
    
    def get_queryset(self):
        """دریافت queryset بر اساس نوع کاربر"""
        from prescription_system.models import Prescription
        
        user = self.request.user
        if user.user_type == 'doctor':
            return Prescription.objects.filter(doctor=user)
        elif user.user_type == 'patient':
            return Prescription.objects.filter(patient=user)
        else:
            return Prescription.objects.none()
    
    def get_serializer_class(self):
        """انتخاب serializer بر اساس action"""
        from prescription_system.serializers import (
            PrescriptionListSerializer,
            PrescriptionDetailSerializer,
            PrescriptionCreateSerializer
        )
        
        if self.action == 'list':
            return PrescriptionListSerializer
        elif self.action == 'create':
            return PrescriptionCreateSerializer
        else:
            return PrescriptionDetailSerializer
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """ایجاد نسخه جدید"""
        try:
            # پردازش با orchestrator
            orchestrator = CentralOrchestrator()
            result = orchestrator.execute_workflow(
                'create_prescription',
                request.data,
                request.user
            )
            
            if result.status == 'completed':
                return Response(
                    result.data,
                    status=status.HTTP_201_CREATED
                )
            else:
                return Response(
                    {'error': 'Failed to create prescription', 'details': result.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Prescription creation error: {str(e)}")
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Async Views (برای Django 4.1+)
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import sync_to_async

@csrf_exempt
async def async_health_check(request):
    """
    نمونه async view برای health check
    """
    try:
        # بررسی‌های async
        db_status = await check_database_async()
        cache_status = await check_cache_async()
        
        return JsonResponse({
            'status': 'healthy',
            'services': {
                'database': db_status,
                'cache': cache_status,
            }
        })
    except Exception as e:
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e)
        }, status=500)


@sync_to_async
def check_database_async():
    """بررسی وضعیت دیتابیس"""
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return 'connected'
    except:
        return 'disconnected'


@sync_to_async
def check_cache_async():
    """بررسی وضعیت cache"""
    try:
        cache.set('health_check', 'ok', 10)
        return 'working' if cache.get('health_check') == 'ok' else 'not working'
    except:
        return 'not working'


# Helper Functions
def process_data(data, user):
    """نمونه تابع پردازش داده"""
    # Implementation
    return {'processed': True, 'data': data}


# Error Response Builder
def build_error_response(error_type, details=None):
    """ساخت پاسخ خطای استاندارد"""
    ingress = APIIngressCore()
    return Response(
        ingress.build_error_response(error_type, details),
        status=get_error_status(error_type)
    )


def get_error_status(error_type):
    """تعیین status code بر اساس نوع خطا"""
    status_mapping = {
        'validation': status.HTTP_400_BAD_REQUEST,
        'authentication': status.HTTP_401_UNAUTHORIZED,
        'permission': status.HTTP_403_FORBIDDEN,
        'not_found': status.HTTP_404_NOT_FOUND,
        'rate_limit': status.HTTP_429_TOO_MANY_REQUESTS,
        'internal': status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    return status_mapping.get(error_type, status.HTTP_500_INTERNAL_SERVER_ERROR)


# نمونه استفاده در urls.py
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    standard_api_endpoint,
    PatientChatView,
    DoctorDashboardView,
    PatientListView,
    PrescriptionViewSet,
    async_health_check,
)

router = DefaultRouter()
router.register(r'prescriptions', PrescriptionViewSet, basename='prescription')

urlpatterns = [
    path('standard/', standard_api_endpoint, name='standard-endpoint'),
    path('chat/', PatientChatView.as_view(), name='patient-chat'),
    path('dashboard/', DoctorDashboardView.as_view(), name='doctor-dashboard'),
    path('patients/', PatientListView.as_view(), name='patient-list'),
    path('health/', async_health_check, name='health-check'),
    path('', include(router.urls)),
]
"""