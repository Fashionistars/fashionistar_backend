from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.tokens import RefreshToken
from asgiref.sync import sync_to_async
import redis
import logging

logger = logging.getLogger('application')

class AuthService:
    """
    Core Authentication Business Logic.
    Handles Login, Token Issuance, and Rate Limiting.
    """

    # --- ASYNC METHODS ---
    @staticmethod
    async def login_async(email_or_phone, password, request=None):
        """
        Authenticates a user asynchronously.
        Accepts raw email_or_phone and password strings.
        """
        try:
            # Authenticate is typically synchronous in Django (DB access)
            # We wrap it.
            user = await sync_to_async(authenticate)(
                request=request, 
                username=email_or_phone, 
                password=password
            )
            
            # Logic fallback if username kwarg fails to route to custom backend fields
            if not user:
                 user = await sync_to_async(authenticate)(
                    email=email_or_phone if '@' in email_or_phone else None,
                    phone=email_or_phone if '@' not in email_or_phone else None,
                    password=password
                 )

            if not user:
                logger.warning(f"⛔ Failed login attempt for {email_or_phone}")
                raise Exception("Invalid credentials.")

            # Update last login
            await sync_to_async(update_last_login)(None, user)

            # Audit logging
            if request:
                user_agent = request.META.get('HTTP_USER_AGENT', '')
                ip_address = request.META.get('REMOTE_ADDR', '')
                logger.info(f"✅ User {user.email} logged in. IP: {ip_address}, UA: {user_agent}")

            # Issue tokens
            refresh = RefreshToken.for_user(user)
            tokens = {
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
            return tokens

        except Exception as e:
            logger.error(f"❌ Login Async Error: {str(e)}")
            raise Exception("Login failed.")

    @staticmethod
    async def get_tokens_async(user):
        """Helper to get tokens for a user instance asynchronously."""
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }

    # --- RATE LIMITING ---
    @staticmethod
    def check_rate_limit(ip_address: str, limit: int = 5, timeout: int = 900):
        """
        Rate Limiting: 5 Failed attempts = 15 minute ban.
        Uses Redis to track attempts per IP.
        """
        try:
            r = redis.Redis.from_url(settings.REDIS_URL)
            key = f"login_attempts:{ip_address}"
            
            attempts = r.get(key)
            if attempts and int(attempts) >= limit:
                logger.warning(f"⛔ Rate Limit Exceeded for IP {ip_address}")
                raise PermissionDenied(f"Too many failed attempts. Try again in {timeout//60} minutes.")
                
        except redis.RedisError as e:
            logger.error(f"Redis Error in Rate Limit: {e}")

    @staticmethod
    def increment_login_failure(ip_address: str, timeout: int = 900):
        try:
            r = redis.Redis.from_url(settings.REDIS_URL)
            key = f"login_attempts:{ip_address}"
            r.incr(key)
            r.expire(key, timeout)
        except Exception:
            pass

    @staticmethod
    def reset_login_failures(ip_address: str):
        try:
            r = redis.Redis.from_url(settings.REDIS_URL)
            r.delete(f"login_attempts:{ip_address}")
        except Exception:
            pass

    # --- SYNC METHODS ---
    @staticmethod
    def login_sync(email_or_phone, password, request=None):
        """
        Authenticates a user synchronously.
        """
        try:
            user = authenticate(username=email_or_phone, password=password)
            # Logic fallback if username kwarg fails to route to custom backend fields
            if not user:
                 # Check if email or phone
                 if '@' in email_or_phone:
                     user = authenticate(email=email_or_phone, password=password)
                 else:
                     user = authenticate(phone=email_or_phone, password=password)

            if not user:
                logger.warning(f"⛔ Failed login attempt for {email_or_phone}")
                raise Exception("Invalid credentials.")

            update_last_login(None, user)

            if request:
                user_agent = request.META.get('HTTP_USER_AGENT', '')
                logger.info(f"✅ User {user.email} logged in (Sync). UA: {user_agent}")

            refresh = RefreshToken.for_user(user)
            return {
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
        except Exception as e:
            logger.error(f"❌ Login Sync Error: {str(e)}")
            raise Exception("Login failed.")
