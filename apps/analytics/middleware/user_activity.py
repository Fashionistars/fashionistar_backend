"""
Middleware برای ردیابی فعالیت‌های کاربران
"""
import logging
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from django.urls import resolve

logger = logging.getLogger(__name__)


class UserActivityTrackingMiddleware(MiddlewareMixin):
    """
    Middleware برای ردیابی فعالیت‌های کاربران
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_response(self, request, response):
        """
        ثبت فعالیت کاربر پس از پاسخ موفق
        """
        # بررسی اینکه آیا analytics فعال است
        if not getattr(settings, 'ANALYTICS_ENABLED', True):
            return response
        
        # فقط برای کاربران احراز هویت شده
        if not request.user.is_authenticated:
            return response
        
        # فقط برای درخواست‌های موفق و مهم
        if response.status_code >= 400:
            return response
        
        # صرفاً برای متدهای مهم
        if request.method not in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return response
        
        try:
            from ..tasks import record_user_activity_async
            
            # تعیین نوع عمل بر اساس متد HTTP
            action_map = {
                'POST': 'create',
                'PUT': 'update',
                'PATCH': 'partial_update',
                'DELETE': 'delete',
                'GET': 'view'
            }
            action = action_map.get(request.method, 'unknown')
            
            # دریافت اطلاعات resource
            try:
                resolved = resolve(request.path_info)
                resource = resolved.namespace or resolved.url_name or 'unknown'
            except:
                resource = request.path_info.split('/')[1] if len(request.path_info.split('/')) > 1 else 'unknown'
            
            # استخراج resource_id از path (در صورت وجود)
            resource_id = None
            try:
                path_parts = [p for p in request.path_info.split('/') if p]
                # جستجوی عدد در path که احتمالاً ID است
                for part in path_parts:
                    if part.isdigit():
                        resource_id = int(part)
                        break
            except:
                pass
            
            # ثبت فعالیت به صورت async
            record_user_activity_async.delay(
                user_id=request.user.id,
                action=action,
                resource=resource,
                resource_id=resource_id,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                session_id=request.session.session_key or '',
                metadata={
                    'path': request.path_info,
                    'method': request.method,
                    'status_code': response.status_code,
                    'content_type': response.get('Content-Type', ''),
                }
            )
            
        except Exception as e:
            # در صورت خطا در ثبت فعالیت، لاگ کنیم اما response را متوقف نکنیم
            logger.error(f"خطا در ثبت فعالیت کاربر: {str(e)}")
        
        return response
    
    def _get_client_ip(self, request):
        """
        دریافت آدرس IP کلاینت از درخواست
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip