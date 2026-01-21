# apps/authentication/services/registration_service/async_service.py

import logging
from apps.authentication.models import UnifiedUser
from apps.authentication.services.otp_service import AsyncOTPService

logger = logging.getLogger('application')

class AsyncRegistrationService:
    """
    Asynchronous Service for User Registration.
    """

    @staticmethod
    async def register_user(data: dict):
        """
        Async Registration Flow.
        1. Create User (Inactive) - Native Async
        2. Generate OTP - Async Wrapper
        Returns: (user, otp)
        """
        try:
            email = data.get('email')
            phone = data.get('phone')
            password = data.get('password')
            role = data.get('role', UnifiedUser.ROLE_CUSTOMER)
            
            # Extract extra fields
            extra_fields = {
                k: v for k, v in data.items() 
                if k not in ['password', 'password2', 'email', 'phone', 'role']
            }

            # 1. Create User (Native Async)
            # No transaction wrapper needed for single object creation
            user = await UnifiedUser.objects.acreate_user(
                email=email,
                phone=phone,
                password=password,
                role=role,
                is_active=False,
                auth_provider=UnifiedUser.PROVIDER_EMAIL if email else UnifiedUser.PROVIDER_PHONE,
                **extra_fields
            )

            # 2. Generate OTP (Async)
            otp = await AsyncOTPService.generate_otp(str(user.id), purpose="activation")
            
            return user, otp

        except Exception as e:
            logger.error(f"❌ Async Registration Failed: {e}")
            raise e
