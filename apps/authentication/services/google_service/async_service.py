# apps/authentication/services/google_service/async_service.py

import logging
import asyncio
from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings
from apps.authentication.models import UnifiedUser

logger = logging.getLogger('application')

class AsyncGoogleAuthService:
    """
    Asynchronous Service for Google OAuth2 (Hybrid Flow).
    """

    @staticmethod
    async def verify_and_login(token: str, role: str = 'client'):
        """
        Verify Google Token and Get/Create User (Async).
        """
        try:
            # 1. Verify with Google (Blocking I/O) -> Offload to thread
            id_info = await asyncio.to_thread(
                id_token.verify_oauth2_token,
                token, requests.Request(), settings.GOOGLE_CLIENT_ID
            )

            email = id_info.get('email')
            if not email:
                raise ValueError("Email not found in Google Token.")

            # 2. Database Operation (Native Async)
            try:
                user = await UnifiedUser.objects.aget(email=email)
                logger.info(f"✅ Google Login: Existing User {email} (Async)")
            except UnifiedUser.DoesNotExist:
                user = await UnifiedUser.objects.acreate(
                    email=email,
                    auth_provider=UnifiedUser.PROVIDER_GOOGLE,
                    is_verified=True,
                    role=role
                )
                logger.info(f"🆕 Google Register: New User {email} (Role: {role}) (Async)")

            return user

        except ValueError as e:
            logger.error(f"❌ Google Token Verification Failed: {e}")
            raise Exception("Invalid Google Token")
        except Exception as e:
            logger.error(f"❌ Unexpected Google Auth Error (Async): {e}", exc_info=True)
            raise Exception("Google authentication failed.")
