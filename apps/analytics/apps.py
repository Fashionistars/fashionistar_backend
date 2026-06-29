"""
تنظیمات اپلیکیشن Analytics
"""
from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """
    کلاس تنظیمات اپ Analytics
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.analytics'
    verbose_name = 'Analytics'
    
    def ready(self):
        """
        تنظیمات هنگام آماده شدن اپ
        """
        pass