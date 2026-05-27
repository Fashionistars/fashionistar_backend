# apps/global_platform_settings/admin_backend/services.py
import logging
from django.db import transaction
from apps.global_platform_settings.models import PlatformSettings, SINGLETON_PK

logger = logging.getLogger(__name__)

class AdminSettingsService:
    @staticmethod
    @transaction.atomic
    def update_settings(data: dict, admin_user) -> PlatformSettings:
        """
        Update the global platform settings.
        """
        settings, _ = PlatformSettings.objects.select_for_update().get_or_create(pk=SINGLETON_PK)
        
        updated_fields = []
        for key, value in data.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
                updated_fields.append(key)
                
        settings.save()
        logger.info("Admin %s updated global platform settings: %s", admin_user.email, updated_fields)
        return settings
