# apps/providers/admin_backend/services.py
import logging
from django.db import transaction
from apps.providers.models import (
    EmailProviderConfig,
    SMSProviderConfig,
    KYCProviderConfig,
    CloudinaryProviderConfig,
    MirrorSizeProviderConfig,
)

logger = logging.getLogger(__name__)

class AdminProvidersService:
    @staticmethod
    @transaction.atomic
    def update_email_config(data: dict, admin_user) -> EmailProviderConfig:
        config, _ = EmailProviderConfig.objects.select_for_update().get_or_create()
        updated_fields = []
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
                updated_fields.append(key)
        config.save()
        logger.info("Admin %s updated EmailProviderConfig: %s", admin_user.email, updated_fields)
        return config

    @staticmethod
    @transaction.atomic
    def update_sms_config(data: dict, admin_user) -> SMSProviderConfig:
        config, _ = SMSProviderConfig.objects.select_for_update().get_or_create()
        updated_fields = []
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
                updated_fields.append(key)
        config.save()
        logger.info("Admin %s updated SMSProviderConfig: %s", admin_user.email, updated_fields)
        return config

    @staticmethod
    @transaction.atomic
    def update_kyc_config(data: dict, admin_user) -> KYCProviderConfig:
        config, _ = KYCProviderConfig.objects.select_for_update().get_or_create()
        updated_fields = []
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
                updated_fields.append(key)
        config.save()
        logger.info("Admin %s updated KYCProviderConfig: %s", admin_user.email, updated_fields)
        return config

    @staticmethod
    @transaction.atomic
    def update_cloudinary_config(data: dict, admin_user) -> CloudinaryProviderConfig:
        config, _ = CloudinaryProviderConfig.objects.select_for_update().get_or_create()
        updated_fields = []
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
                updated_fields.append(key)
        config.save()
        logger.info("Admin %s updated CloudinaryProviderConfig: %s", admin_user.email, updated_fields)
        return config

    @staticmethod
    @transaction.atomic
    def update_mirrorsize_config(data: dict, admin_user) -> MirrorSizeProviderConfig:
        config, _ = MirrorSizeProviderConfig.objects.select_for_update().get_or_create()
        updated_fields = []
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
                updated_fields.append(key)
        config.save()
        logger.info("Admin %s updated MirrorSizeProviderConfig: %s", admin_user.email, updated_fields)
        return config
