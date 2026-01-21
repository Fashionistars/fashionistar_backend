# apps/authentication/services/registration_service/sync_service.py

import logging
from django.db import transaction
from apps.authentication.models import UnifiedUser
from apps.authentication.services.otp_service import SyncOTPService

logger = logging.getLogger('application')

class SyncRegistrationService:
    """
    Synchronous Service for User Registration.
    """

    @staticmethod
    def register_user(data: dict):
        """
        Sync Registration Flow.
        1. Create User (Inactive) - Atomic
        2. Generate OTP
        Returns: (user, otp)
        """
        try:
            # 1. Create User Atomically
            user = SyncRegistrationService._create_user_db(data)
            
            # 2. Generate OTP using Sync Service
            otp = SyncOTPService.generate_otp(str(user.id), purpose="activation")
            
            # Note: Notification dispatch should be handled by the controller (View) 
            # or a separate NotificationService called here. For now, we return OTP.
            
            return user, otp

        except Exception as e:
            logger.error(f"❌ Sync Registration Failed: {e}")
            raise e

    @staticmethod
    def _create_user_db(data: dict):
        """
        Internal Sync User Creation.
        """
        with transaction.atomic():
            email = data.get('email')
            phone = data.get('phone')
            password = data.get('password')
            role = data.get('role', UnifiedUser.ROLE_CUSTOMER) # Default to customer
            
            # Extract extra fields
            extra_fields = {
                k: v for k, v in data.items() 
                if k not in ['password', 'password2', 'email', 'phone', 'role']
            }

            user = UnifiedUser.objects.create_user(
                email=email,
                phone=phone,
                password=password,
                role=role,
                is_active=False, # Wait for OTP
                auth_provider=UnifiedUser.PROVIDER_EMAIL if email else UnifiedUser.PROVIDER_PHONE,
                **extra_fields
            )
            return user
