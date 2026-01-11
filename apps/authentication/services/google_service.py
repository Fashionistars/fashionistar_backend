from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings
from apps.authentication.models import UnifiedUser
from asgiref.sync import sync_to_async
from asgiref.sync import async_to_sync
import logging

logger = logging.getLogger('application')

class GoogleAuthService:
    """
    Service for handling Google OAuth2 (Hybrid Flow).
    Verifies ID Tokens on the server side.
    """

    @staticmethod
    async def verify_and_login_async(token: str, role: str = 'client'):
        """
        Async method to verify Google Token and Get/Create User.
        Strictly enforces that the user cannot change role if they already exist.
        """
        try:
            # 1. Verify with Google (IO Bound)
            # requests.Request() is synchronous, so we might wrap if needed for strict non-blocking
            id_info = id_token.verify_oauth2_token(
                token, requests.Request(), settings.GOOGLE_CLIENT_ID
            )

            email = id_info.get('email')
            if not email:
                raise ValueError("Email not found in Google Token.")

            # 2. Database Operation (Async)
            # Check if user exists
            try:
                user = await UnifiedUser.objects.aget(email=email)
                logger.info(f"✅ Google Login: Existing User {email}")
                # We do NOT update the role for existing users.
            except UnifiedUser.DoesNotExist:
                # Create new user
                user = await UnifiedUser.objects.acreate(
                    email=email,
                    # Set username to email for consistency if needed, though model ignores it
                    auth_provider=UnifiedUser.PROVIDER_GOOGLE,
                    is_verified=True, # Google emails are verified
                    role=role
                )
                logger.info(f"🆕 Google Register: New User {email} (Role: {role})")

            return user

        except ValueError as e:
            logger.error(f"❌ Google Token Verification Failed: {e}")
            raise Exception("Invalid Google Token")
        except Exception as e:
            logger.error(f"❌ Unexpected Google Auth Error: {e}", exc_info=True)
            raise Exception("Google authentication failed.")

    @staticmethod
    def verify_and_login_sync(token: str, role: str = 'client'):
        """
        Synchronous wrapper for verify_and_login.
        """
        return async_to_sync(GoogleAuthService.verify_and_login_async)(token, role)
