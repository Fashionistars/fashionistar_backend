# apps/devops/apps.py
"""
AppConfig configuration for the devops app.
"""
from django.apps import AppConfig


class DevopsConfig(AppConfig):
    """Configuration class for the devops app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.devops'
    verbose_name = 'DevOps Management'
    
    def ready(self):
        """Initial settings after app load."""
        try:
            import apps.devops.signals  # noqa: F401
        except ImportError:
            pass