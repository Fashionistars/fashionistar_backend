from apps.authentication.models import UnifiedUser
from apps.authentication.types.auth_schemas import RegistrationSchema
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
    async def register_user_async(data: RegistrationSchema):
        """
        Async Registration Flow.
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
            # In a real sync task, we would call EmailManager.send_activation_email(user, otp)
            # We return the user and otp (or status) for the controller to handle response
            return user, otp

        except Exception as e:
            logger.error(f"❌ Async Registration Failed: {e}")
            raise e

    @staticmethod
    def _create_user_atomic(data: RegistrationSchema):
        """
        Internal Sync method to handle DB Atomicity.
        """
        with transaction.atomic():
            # Using create_user helper if available or manual creation
            # AbstractUser manager usually has create_user
            user = UnifiedUser.objects.create_user(
                email=data.email,
                phone=data.phone,
                password=data.password,
                role=data.role,
                is_active=False, # Wait for OTP
                auth_provider=UnifiedUser.PROVIDER_EMAIL if data.email else UnifiedUser.PROVIDER_PHONE
            )
            return user

    @staticmethod
    def register_user_sync(data: RegistrationSchema):
        """Sync Wrapper for compatibility."""
        return RegistrationService._create_user_atomic(data)
