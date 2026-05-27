# apps/global_platform_settings/admin_backend/selectors.py
import logging
from apps.global_platform_settings.cache import get_platform_settings
from apps.global_platform_settings.models import PlatformSettings, SINGLETON_PK

logger = logging.getLogger(__name__)

class AdminSettingsSelector:
    @classmethod
    def get_settings(cls) -> PlatformSettings:
        """
        Retrieve global platform settings.
        """
        return get_platform_settings()

    # --- Async Support ---
    
    @classmethod
    async def aget_settings(cls) -> PlatformSettings:
        """Async version of get_settings."""
        # Using aget() or fallback from cache
        try:
            return await PlatformSettings.objects.aget(pk=SINGLETON_PK)
        except PlatformSettings.DoesNotExist:
            return get_platform_settings()
