# apps/authentication/services/google_service/sync_service.py

import logging
from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings
from apps.authentication.models import UnifiedUser

logger = logging.getLogger('application')

class SyncGoogleAuthService:
    """
    Synchronous Service for Google OAuth2 (Hybrid Flow).
    """

    @staticmethod
    def verify_and_login(token: str, role: str = 'client'):
        """
        Verify Google Token and Get/Create User (Sync).
        """
        try:
            # 1. Verify with Google
            id_info = id_token.verify_oauth2_token(
                token, requests.Request(), settings.GOOGLE_CLIENT_ID
            )

            email = id_info.get('email')
            if not email:
                raise ValueError("Email not found in Google Token.")

            # 2. Database Operation
            try:
                user = UnifiedUser.objects.get(email=email)
                logger.info(f"✅ Google Login: Existing User {email}")
            except UnifiedUser.DoesNotExist:
                user = UnifiedUser.objects.create(
                    email=email,
                    auth_provider=UnifiedUser.PROVIDER_GOOGLE,
                    is_verified=True,
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
