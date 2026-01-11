"""
App configuration for the common app.

This module defines the configuration for the 'common' Django app,
which provides shared utilities, models, and permissions across the project.
"""

from django.apps import AppConfig


class CommonConfig(AppConfig):
    """
    Configuration class for the common app.

    This class sets up the common app with its name and verbose name,
    ensuring proper integration with Django's app registry.

    Attributes:
        default_auto_field (str): Default auto field type for models in this app.
        name (str): The name of the app as used in Django settings.
        verbose_name (str): Human-readable name for the app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.common'
    verbose_name = 'Common Utilities'
