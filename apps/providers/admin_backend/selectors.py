# apps/providers/admin_backend/selectors.py
import logging
from apps.providers.models import (
    EmailProviderConfig,
    SMSProviderConfig,
    KYCProviderConfig,
    CloudinaryProviderConfig,

)

logger = logging.getLogger(__name__)

class AdminProvidersSelector:
    @classmethod
    def get_email_config(cls) -> EmailProviderConfig:
        config, _ = EmailProviderConfig.objects.get_or_create()
        return config

    @classmethod
    def get_sms_config(cls) -> SMSProviderConfig:
        config, _ = SMSProviderConfig.objects.get_or_create()
        return config

    @classmethod
    def get_kyc_config(cls) -> KYCProviderConfig:
        config, _ = KYCProviderConfig.objects.get_or_create()
        return config

    @classmethod
    def get_cloudinary_config(cls) -> CloudinaryProviderConfig:
        config, _ = CloudinaryProviderConfig.objects.get_or_create()
        return config



    # --- Async Support ---

    @classmethod
    async def aget_email_config(cls) -> EmailProviderConfig:
        try:
            return await EmailProviderConfig.objects.afirst() or await EmailProviderConfig.objects.acreate()
        except Exception:
            return cls.get_email_config()

    @classmethod
    async def aget_sms_config(cls) -> SMSProviderConfig:
        try:
            return await SMSProviderConfig.objects.afirst() or await SMSProviderConfig.objects.acreate()
        except Exception:
            return cls.get_sms_config()

    @classmethod
    async def aget_kyc_config(cls) -> KYCProviderConfig:
        try:
            return await KYCProviderConfig.objects.afirst() or await KYCProviderConfig.objects.acreate()
        except Exception:
            return cls.get_kyc_config()

    @classmethod
    async def aget_cloudinary_config(cls) -> CloudinaryProviderConfig:
        try:
            return await CloudinaryProviderConfig.objects.afirst() or await CloudinaryProviderConfig.objects.acreate()
        except Exception:
            return cls.get_cloudinary_config()


