# apps/scheduler/apps.py
"""
AppConfig configuration for the scheduler app.
"""
from django.apps import AppConfig


class SchedulerConfig(AppConfig):
    """Configuration class for the scheduler app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.scheduler'
    verbose_name = 'برنامه‌ریزی کارها'
    
    def ready(self):
        """Prepare the app when loaded."""
        pass