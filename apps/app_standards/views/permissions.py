"""
الگوهای Permission سفارشی
Custom Permission Patterns
"""

from rest_framework import permissions
from django.contrib.auth import get_user_model
from django.core.cache import cache
from unified_access.services import AccessControlService
import logging
import time


User = get_user_model()
logger = logging.getLogger(__name__)


class BasePermission(permissions.BasePermission):
    """
    کلاس پایه برای permissions سفارشی
    """
    message = 'دسترسی غیرمجاز'
    
    def has_permission(self, request, view):
        """بررسی دسترسی سطح view"""
        if not request.user or not request.user.is_authenticated:
            self.message = 'احراز هویت الزامی است'
            return False
        
        if not request.user.is_active:
            self.message = 'حساب کاربری غیرفعال است'
            return False
            
        return True


class IsPatient(BasePermission):
    """
    دسترسی فقط برای بیماران
    """
    message = 'دسترسی فقط برای بیماران'
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
            
        return request.user.user_type == 'patient'


class IsDoctor(BasePermission):
    """
    دسترسی فقط برای پزشکان
    """
    message = 'دسترسی فقط برای پزشکان'
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
            
        return request.user.user_type == 'doctor'


class IsOwner(BasePermission):
    """
    دسترسی فقط برای مالک object
    """
    message = 'دسترسی فقط برای مالک'
    
    def has_object_permission(self, request, view, obj):
        # بررسی فیلدهای مختلف ownership
        owner_fields = ['user', 'owner', 'created_by', 'patient', 'doctor']
        
        for field in owner_fields:
            if hasattr(obj, field):
                owner = getattr(obj, field)
                if owner == request.user:
                    return True
                    
        return False


class IsOwnerOrDoctor(BasePermission):
    """
    دسترسی برای مالک یا پزشک مربوطه
    """
    message = 'دسترسی برای مالک یا پزشک مربوطه'
    
    def has_object_permission(self, request, view, obj):
        # مالک
        if hasattr(obj, 'patient') and obj.patient == request.user:
            return True
            
        # پزشک
        if hasattr(obj, 'doctor') and obj.doctor == request.user:
            return True
            
        # پزشک دارای دسترسی به بیمار
        if hasattr(obj, 'patient') and request.user.user_type == 'doctor':
            access_service = AccessControlService()
            return access_service.has_patient_access(request.user, obj.patient)
            
        return False


class HasActiveSubscription(BasePermission):
    """
    دسترسی فقط با اشتراک فعال
    """
    message = 'اشتراک فعال الزامی است'
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
            
        # بررسی cache
        cache_key = f"user_subscription:{request.user.id}"
        has_subscription = cache.get(cache_key)
        
        if has_subscription is None:
            # بررسی از دیتابیس
            from unified_billing.models import Subscription
            has_subscription = Subscription.objects.filter(
                user=request.user,
                status='active'
            ).exists()
            
            # ذخیره در cache
            cache.set(cache_key, has_subscription, 300)  # 5 minutes
            
        return has_subscription


class RateLimitPermission(BasePermission):
    """
    محدودیت نرخ درخواست
    """
    rate = '100/hour'  # default rate
    message = 'تعداد درخواست‌ها بیش از حد مجاز'
    
    def get_rate(self):
        """دریافت نرخ محدودیت"""
        return self.rate
    
    def get_cache_key(self, request):
        """تولید کلید cache"""
        if request.user.is_authenticated:
            ident = request.user.id
        else:
            ident = self.get_ident(request)
            
        return f"rate_limit:{self.__class__.__name__}:{ident}"
    
    def get_ident(self, request):
        """دریافت شناسه برای کاربران ناشناس"""
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        remote_addr = request.META.get('REMOTE_ADDR')
        return xff.split(',')[0] if xff else remote_addr
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
            
        # پارس rate
        num_requests, period = self.parse_rate(self.get_rate())
        
        # بررسی محدودیت
        cache_key = self.get_cache_key(request)
        history = cache.get(cache_key, [])
        now = int(time.time())
        
        # حذف درخواست‌های قدیمی
        history = [timestamp for timestamp in history if timestamp > now - period]
        
        if len(history) >= num_requests:
            return False
            
        # اضافه کردن درخواست جدید
        history.append(now)
        cache.set(cache_key, history, period)
        
        return True
    
    def parse_rate(self, rate):
        """پارس رشته rate"""
        if not rate:
            return (None, None)
            
        num, period = rate.split('/')
        num_requests = int(num)
        
        duration = {
            'second': 1, 'minute': 60, 'hour': 3600, 'day': 86400
        }
        
        period_name = period.rstrip('s')  # Remove plural
        period_seconds = duration.get(period_name, 60)
        
        return (num_requests, period_seconds)


class DynamicPermission(BasePermission):
    """
    دسترسی پویا بر اساس قوانین تعریف شده
    """
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
            
        # دریافت قوانین از AccessControlService
        access_service = AccessControlService()
        
        # بررسی action
        action = self.get_action(request, view)
        resource = self.get_resource(view)
        
        return access_service.check_permission(
            user=request.user,
            resource=resource,
            action=action
        )
    
    def get_action(self, request, view):
        """تعیین action بر اساس HTTP method"""
        method_actions = {
            'GET': 'view',
            'POST': 'create',
            'PUT': 'update',
            'PATCH': 'update',
            'DELETE': 'delete',
        }
        return method_actions.get(request.method, 'view')
    
    def get_resource(self, view):
        """تعیین resource از view"""
        if hasattr(view, 'get_queryset'):
            model = view.get_queryset().model
            return model.__name__.lower()
        return 'unknown'


class GroupPermission(BasePermission):
    """
    دسترسی بر اساس گروه کاربری
    """
    allowed_groups = []  # باید در subclass تعریف شود
    message = 'کاربر در گروه مجاز نیست'
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
            
        user_groups = request.user.groups.values_list('name', flat=True)
        return any(group in self.allowed_groups for group in user_groups)


class TimeBasedPermission(BasePermission):
    """
    دسترسی بر اساس زمان
    """
    allowed_hours = (8, 20)  # 8 AM to 8 PM
    message = 'دسترسی در این ساعت مجاز نیست'
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
            
        from django.utils import timezone
        current_hour = timezone.now().hour
        
        return self.allowed_hours[0] <= current_hour < self.allowed_hours[1]


class IPWhitelistPermission(BasePermission):
    """
    دسترسی بر اساس IP whitelist
    """
    message = 'دسترسی از این IP مجاز نیست'
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
            
        # دریافت IP
        ip = self.get_client_ip(request)
        
        # بررسی whitelist
        from django.conf import settings
        whitelist = getattr(settings, 'IP_WHITELIST', [])
        
        return ip in whitelist
    
    def get_client_ip(self, request):
        """دریافت IP کلاینت"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class CompositePermission(BasePermission):
    """
    ترکیب چند permission
    """
    permissions = []  # لیست permission classes
    require_all = True  # آیا همه permissions باید True باشند
    
    def has_permission(self, request, view):
        results = []
        
        for permission_class in self.permissions:
            permission = permission_class()
            results.append(permission.has_permission(request, view))
        
        if self.require_all:
            return all(results)
        else:
            return any(results)
    
    def has_object_permission(self, request, view, obj):
        results = []
        
        for permission_class in self.permissions:
            permission = permission_class()
            results.append(permission.has_object_permission(request, view, obj))
        
        if self.require_all:
            return all(results)
        else:
            return any(results)


# مثال‌های استفاده

class DoctorWithActiveSubscription(CompositePermission):
    """پزشک با اشتراک فعال"""
    permissions = [IsDoctor, HasActiveSubscription]
    require_all = True


class PatientOrDoctor(CompositePermission):
    """بیمار یا پزشک"""
    permissions = [IsPatient, IsDoctor]
    require_all = False


class AdminGroupPermission(GroupPermission):
    """دسترسی گروه ادمین"""
    allowed_groups = ['admin', 'superadmin']


class BusinessHoursPermission(TimeBasedPermission):
    """دسترسی در ساعات کاری"""
    allowed_hours = (9, 17)  # 9 AM to 5 PM
    message = 'دسترسی فقط در ساعات کاری مجاز است'


class AIRateLimitPermission(RateLimitPermission):
    """محدودیت نرخ برای درخواست‌های AI"""
    rate = '20/hour'
    message = 'تعداد درخواست‌های AI بیش از حد مجاز'


# Helper functions

def check_object_permission(user, obj, permission_type='view'):
    """
    بررسی دسترسی به object
    """
    access_service = AccessControlService()
    
    resource_type = obj.__class__.__name__.lower()
    resource_id = str(obj.pk)
    
    return access_service.check_permission(
        user=user,
        resource=f"{resource_type}:{resource_id}",
        action=permission_type
    )


def require_permission(permission_type):
    """
    دکوراتور برای بررسی دسترسی
    """
    def decorator(func):
        def wrapper(request, *args, **kwargs):
            if not check_permission(request.user, permission_type):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('دسترسی غیرمجاز')
            return func(request, *args, **kwargs)
        return wrapper
    return decorator


import time  # اضافه کردن import که فراموش شده بود