from apps.authentication.models import UnifiedUser
from apps.authentication.services.otp_service import OTPService
from asgiref.sync import sync_to_async
from django.db import transaction
import logging

logger = logging.getLogger('application')

class RegistrationService:
    """
    Handles User Registration with Atomic Transactions and OTP dispatch.
    """

    @staticmethod
    async def register_user_async(data: dict):
        """
        Async Registration Flow.
        Accepts a dictionary of validated data.
        1. Create User (Inactive)
        2. Generate OTP
        3. Send Notification (Async Task)
        """
        try:
            # Wrap DB creation in sync_to_async since Django ORM atomic is sync
            user = await sync_to_async(RegistrationService._create_user_atomic)(data)
            
            # Generate OTP (Redis)
            otp = OTPService.generate_otp(user.id, purpose="activation")
            
            # Send OTP (Logic would invoke Email/SMS manager appropriately)
            # We return the user and otp (or status) for the controller to handle response
            return user, otp

        except Exception as e:
            logger.error(f"❌ Async Registration Failed: {e}")
            raise e

    @staticmethod
    def _create_user_atomic(data: dict):
        """
        Internal Sync method to handle DB Atomicity.
        """
        with transaction.atomic():
            email = data.get('email')
            phone = data.get('phone')
            password = data.get('password')
            role = data.get('role')
            
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

    @staticmethod
    def register_user_sync(data: dict):
        """Sync Wrapper for compatibility."""
        return RegistrationService._create_user_atomic(data)
