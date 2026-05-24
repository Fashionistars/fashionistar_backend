from django.apps import AppConfig


class SchedulerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scheduler'
    verbose_name = 'برنامه‌ریزی کارها'
    
    def ready(self):
        """
        آماده‌سازی اپ در زمان راه‌اندازی
        """
        # Import signal handlers here if needed
        pass