# apps/search/apps.py
"""
Search app configuration.
"""

from django.apps import AppConfig


class SearchConfig(AppConfig):
    """Configuration class for the search app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.search'
    verbose_name = 'Search'

    def ready(self):
        """Prepare the search app (no-op for now)."""
        pass
