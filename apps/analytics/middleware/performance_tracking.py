"""
Middleware برای ردیابی عملکرد درخواست‌های API
"""
import time
import logging
from django.utils.deprecation import MiddlewareMixin
from django.urls import resolve
from django.conf import settings

logger = logging.getLogger(__name__)


class PerformanceTrackingMiddleware(MiddlewareMixin):
    """
    Middleware برای ردیابی زمان پاسخ و ثبت متریک‌های عملکرد
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        """
        شروع ردیابی زمان درخواست
        """
        request._analytics_start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """
        پایان ردیابی و ثبت متریک عملکرد
        """
        # بررسی اینکه آیا analytics فعال است
        if not getattr(settings, 'ANALYTICS_ENABLED', True):
            return response
        
        # محاسبه زمان پاسخ
        if hasattr(request, '_analytics_start_time'):
            response_time_ms = int((time.time() - request._analytics_start_time) * 1000)
        else:
            response_time_ms = 0
        
        # ثبت متریک عملکرد به صورت async
        try:
            from ..tasks import record_performance_metric_async
            
            # دریافت اطلاعات endpoint
            try:
                url_name = resolve(request.path_info).url_name or 'unknown'
                endpoint = f"{resolve(request.path_info).namespace}:{url_name}" if resolve(request.path_info).namespace else url_name
            except:
                endpoint = request.path_info
            
            # ثبت متریک به صورت async
            record_performance_metric_async.delay(
                endpoint=endpoint,
                method=request.method,
                response_time_ms=response_time_ms,
                status_code=response.status_code,
                user_id=request.user.id if request.user.is_authenticated else None,
                error_message=getattr(response, 'reason_phrase', '') if response.status_code >= 400 else '',
                metadata={
                    'path': request.path_info,
                    'query_params': dict(request.GET),
                    'content_type': response.get('Content-Type', ''),
                    'content_length': response.get('Content-Length', 0),
                }
            )
            
        except Exception as e:
            # در صورت خطا در ثبت متریک، لاگ کنیم اما response را متوقف نکنیم
            logger.error(f"خطا در ثبت متریک عملکرد: {str(e)}")
        
        return response