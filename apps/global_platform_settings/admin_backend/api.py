# apps/global_platform_settings/admin_backend/api.py
import logging
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from .selectors import AdminSettingsSelector
from .schemas import PlatformSettingsSchema

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Global_platform_settings"])

@router.get("/", response=PlatformSettingsSchema, summary="Admin: Retrieve Global Platform Settings", auth=admin_auth)
async def get_admin_settings(request):
    """
    Retrieve global platform settings.
    """
    settings = await AdminSettingsSelector.aget_settings()
    return settings

