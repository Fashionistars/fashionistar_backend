# apps/authentication/services/auth_service/async_service.py

import logging
import asyncio
from django.contrib.auth import aauthenticate
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from .sync_service import SyncAuthService

logger = logging.getLogger('application')

class AsyncAuthService:
    """
    Asynchronous Core Authentication Business Logic.
    Handles Login, Token Issuance, and Rate Limiting using Async Django features.
    """

    @staticmethod
    async def login(email_or_phone, password, request=None):
        """
        Authenticates a user asynchronously using Django 5.0+ `aauthenticate`.
        """
        try:
            # 1. Authenticate using native async methods
            user = await aauthenticate(request=request, username=email_or_phone, password=password)
            
            if not user:
                 if '@' in email_or_phone:
                     user = await aauthenticate(request=request, email=email_or_phone, password=password)
                 else:
                     user = await aauthenticate(request=request, phone=email_or_phone, password=password)

            if not user:
                logger.warning(f"⛔ Failed login attempt for {email_or_phone}")
                raise Exception("Invalid credentials.")

            # 2. Update last login (Manual update as update_last_login is sync)
            # We can use the async save method on the user model directly.
            user.last_login =  __import__('django.utils.timezone', fromlist=['now']).now()
            await user.asave(update_fields=['last_login'])

            # 3. Audit Logging
            if request:
                user_agent = request.META.get('HTTP_USER_AGENT', '')
                ip_address = request.META.get('REMOTE_ADDR', '')
                logger.info(f"✅ User {user.email} logged in (Async). IP: {ip_address}, UA: {user_agent}")

            # 4. Issue Tokens (SimpleJWT is sync, does not touch DB for signing usually, but verify_user might)
            # SimpleJWT's RefreshToken.for_user is generally sync cpu-bound.
            # We wrap it just in case it hits the DB (which it might for blacklist checks)
            # However, `RefreshToken.for_user(user)` itself creates the objects in memory
            # The 'blacklist' app might hit DB on token creation? No, only on refresh/logout.
            # So this is safe-ish, but let's wrap strictly to avoid "SyncOnlyOperation" if it touches DB.
            
            refresh = await asyncio.to_thread(RefreshToken.for_user, user)
            
            tokens = {
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
            return tokens

        except Exception as e:
            logger.error(f"❌ Login Async Error: {str(e)}")
            raise Exception("Login failed.")

    @staticmethod
    async def get_tokens(user):
        """Helper to get tokens for a user instance asynchronously."""
        refresh = await asyncio.to_thread(RefreshToken.for_user, user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }

    # --- RATE LIMITING DELEGATES ---
    @staticmethod
    async def check_rate_limit(ip_address: str, limit: int = 5, timeout: int = 900):
        await asyncio.to_thread(
            SyncAuthService.check_rate_limit,
            ip_address, limit, timeout
        )

    @staticmethod
    async def increment_login_failure(ip_address: str, timeout: int = 900):
         await asyncio.to_thread(
            SyncAuthService.increment_login_failure,
            ip_address, timeout
        )

    @staticmethod
    async def reset_login_failures(ip_address: str):
        await asyncio.to_thread(
            SyncAuthService.reset_login_failures,
             ip_address
        )
