"""
تنظیمات اپلیکیشن DevOps برای مدیریت زیرساخت و deployment
"""
from django.apps import AppConfig


class DevopsConfig(AppConfig):
    """پیکربندی اپلیکیشن DevOps"""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'devops'
    verbose_name = 'مدیریت DevOps'
    
    def ready(self):
        """تنظیمات اولیه پس از بارگذاری اپلیکیشن"""
        try:
            import devops.signals
        except ImportError:
            pass