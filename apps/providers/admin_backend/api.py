# apps/providers/admin_backend/api.py
import logging
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from .selectors import AdminProvidersSelector
from .schemas import AllProvidersSummarySchema

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Providers"])

@router.get("/", response=AllProvidersSummarySchema, summary="Admin: Retrieve All Provider Configs Summary", auth=admin_auth)
async def get_all_providers(request):
    """
    Retrieve configurations for all providers (Email, SMS, KYC, Cloudinary, MirrorSize).
    """
    email_cfg = await AdminProvidersSelector.aget_email_config()
    sms_cfg = await AdminProvidersSelector.aget_sms_config()
    kyc_cfg = await AdminProvidersSelector.aget_kyc_config()
    cloudinary_cfg = await AdminProvidersSelector.aget_cloudinary_config()
    mirrorsize_cfg = await AdminProvidersSelector.aget_mirrorsize_config()

    return {
        "email": email_cfg,
        "sms": sms_cfg,
        "kyc": kyc_cfg,
        "cloudinary": cloudinary_cfg,
        "mirrorsize": mirrorsize_cfg,
    }
