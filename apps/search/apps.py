"""
تنظیمات اپلیکیشن search
Search app configuration
"""

from django.apps import AppConfig


class SearchConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'search'
    verbose_name = 'Search'

    def ready(self):
        """
        آماده‌سازی اپلیکیشن جستجو
        """
        # فعلاً عملیاتی نیاز نیست
        pass

