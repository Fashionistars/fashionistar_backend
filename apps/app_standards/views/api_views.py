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
from app_standards.permissions import IsClient, IsVendor
from app_standards.four_cores import APIIngressCore, CentralOrchestrator
from apps.client.models.client_profile import ClientProfile
from apps.custom_order.models import CustomOrder
from rest_framework import serializers
import logging
from django.http import JsonResponse

class ClientProfileFallbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientProfile
        fields = '__all__'

class CustomOrderFallbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomOrder
        fields = '__all__'

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
class ClientChatView(BaseAPIView):
    """
    نمونه View برای چت مشتری
    """
    permission_classes = [IsAuthenticated, IsClient]
    throttle_classes = [StandardUserThrottle, AIRequestThrottle]
    
    def post(self, request):
        """ارسال پیام چت"""
        try:
            # اعتبارسنجی
            from apps.chatbot.serializers import MessageSerializer
            is_valid, data = self.ingress.validate_request(
                request.data,
                MessageSerializer
            )
            
            if not is_valid:
                return Response(
                    self.ingress.build_error_response('validation', data),
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # اجرای workflow
            result = self.orchestrator.execute_workflow(
                'client_chat',
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
                
        except Exception:
            logger.exception("Chat processing error")
            return Response(
                self.ingress.build_error_response('internal'),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
 
 
class VendorDashboardView(BaseAPIView):
    """
    داشبورد فروشنده
    """
    permission_classes = [IsAuthenticated, IsVendor]
    
    def get(self, request):
        """دریافت اطلاعات داشبورد"""
        try:
            # بررسی cache
            cache_key = f"vendor_dashboard:{request.user.id}"
            cached_data = cache.get(cache_key)
            
            if cached_data:
                return Response(cached_data)
            
            # جمع‌آوری داده‌ها
            dashboard_data = {
                'today_orders': self._get_today_orders(request.user),
                'pending_offers': self._get_pending_offers(request.user),
                'client_messages': self._get_client_messages(request.user),
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
    
    def _get_today_orders(self, vendor):
        """دریافت سفارش‌های امروز"""
        # Implementation
        return []
    
    def _get_pending_offers(self, vendor):
        """دریافت آفر‌های در انتظار"""
        # Implementation
        return []
    
    def _get_client_messages(self, vendor):
        """دریافت پیام‌های مشتریان"""
        # Implementation
        return []
    
    def _get_statistics(self, vendor):
        """دریافت آمار"""
        # Implementation
        return {}
 
 
# Generic Views
class ClientListView(ListAPIView):
    """
    لیست مشتریان برای فروشنده
    """
    permission_classes = [IsAuthenticated, IsVendor]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        """دریافت queryset بر اساس فروشنده"""
        return ClientProfile.objects.filter(
            is_active=True
        )
    
    def get_serializer_class(self):
        """انتخاب serializer"""
        return ClientProfileFallbackSerializer
 
 
# ViewSets
class CustomOrderViewSet(ModelViewSet):
    """
    ViewSet برای مدیریت سفارش‌های شخصی‌سازی شده
    """
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    
    def get_permissions(self):
        """تعیین دسترسی‌ها بر اساس action"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAuthenticated, IsVendor]
        return super().get_permissions()
    
    def get_queryset(self):
        """دریافت queryset بر اساس نوع کاربر"""
        user = self.request.user
        role = getattr(user, 'role', '')
        if role == 'vendor':
            return CustomOrder.objects.filter(vendor=user)
        elif role == 'client':
            return CustomOrder.objects.filter(client=user)
        else:
            return CustomOrder.objects.none()
    
    def get_serializer_class(self):
        """انتخاب serializer بر اساس action"""
        return CustomOrderFallbackSerializer
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """ایجاد سفارش جدید"""
        try:
            # پردازش با orchestrator
            orchestrator = CentralOrchestrator()
            result = orchestrator.execute_workflow(
                'create_custom_order',
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
                    {'error': 'Failed to create custom order', 'details': result.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
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