# apps/authentication/services/auth_service/sync_service.py

import logging
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.tokens import RefreshToken
from utilities.django_redis import get_redis_connection_safe

logger = logging.getLogger('application')

class SyncAuthService:
    """
    Synchronous Core Authentication Business Logic.
    Handles Login, Token Issuance, and Rate Limiting.
    """

    @staticmethod
    def login(email_or_phone, password, request=None):
        """
        Authenticates a user synchronously.
        """
        try:
            # First attempt: Pass email_or_phone as username (standard Django behavior)
            user = authenticate(request=request, username=email_or_phone, password=password)
            
            # Second attempt: explicitly route to 'email' or 'phone' kwarg for custom backends
            if not user:
                 if '@' in email_or_phone:
                     user = authenticate(request=request, email=email_or_phone, password=password)
                 else:
                     # Remove specific phone formatting or let backend handle it
                     user = authenticate(request=request, phone=email_or_phone, password=password)

            if not user:
                logger.warning(f"⛔ Failed login attempt for {email_or_phone}")
                # We do NOT raise strict logical exception here, usually verify at view, 
                # but for service architecture, returning None is cleaner, or raising a specific Auth Exception.
                # However, to match existing pattern:
                raise Exception("Invalid credentials.")

            update_last_login(None, user)

            if request:
                user_agent = request.META.get('HTTP_USER_AGENT', '')
                ip_address = request.META.get('REMOTE_ADDR', '')
                logger.info(f"✅ User {user.email} logged in (Sync). IP: {ip_address}, UA: {user_agent}")

            refresh = RefreshToken.for_user(user)
            return {
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
        except Exception as e:
            logger.error(f"❌ Login Sync Error: {str(e)}")
            raise Exception("Login failed.")

    # --- RATE LIMITING ---
    @staticmethod
    def check_rate_limit(ip_address: str, limit: int = 5, timeout: int = 900):
        """
        Rate Limiting: 5 Failed attempts = 15 minute ban.
        """
        try:
            r = get_redis_connection_safe()
            if not r:
                 logger.warning("Redis unavailable for rate limiting, skipping.")
                 return

            key = f"login_attempts:{ip_address}"
            
            attempts = r.get(key)
            if attempts and int(attempts) >= limit:
                logger.warning(f"⛔ Rate Limit Exceeded for IP {ip_address}")
                raise PermissionDenied(f"Too many failed attempts. Try again in {timeout//60} minutes.")
                
        except Exception as e:
             if isinstance(e, PermissionDenied):
                 raise
             logger.error(f"Redis Error in Rate Limit: {e}")

    @staticmethod
    def increment_login_failure(ip_address: str, timeout: int = 900):
        try:
            r = get_redis_connection_safe()
            if r:
                key = f"login_attempts:{ip_address}"
                r.incr(key)
                r.expire(key, timeout)
        except Exception:
            pass

    @staticmethod
    def reset_login_failures(ip_address: str):
        try:
            r = get_redis_connection_safe()
            if r:
                r.delete(f"login_attempts:{ip_address}")
        except Exception:
            pass
