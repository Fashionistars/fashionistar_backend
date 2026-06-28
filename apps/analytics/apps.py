"""
تنظیمات اپلیکیشن Analytics
"""
from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """
    کلاس تنظیمات اپ Analytics
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics'
    verbose_name = 'تحلیل‌ها و آمارگیری'
    
    def ready(self):
        """
        تنظیمات هنگام آماده شدن اپ
        """
        pass