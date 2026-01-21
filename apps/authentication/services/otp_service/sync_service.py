# apps/authentication/services/otp_service/sync_service.py

import logging
import secrets
from django.conf import settings
from utilities.django_redis import get_redis_connection_safe, encrypt_otp, decrypt_otp, generate_numeric_otp

logger = logging.getLogger('application')

class SyncOTPService:
    """
    Synchronous Service for handling One-Time Passwords (OTP).
    - Generates 6-digit numeric codes.
    - Encrypts codes before storage.
    - Stores in Redis with TTL (Time To Live).
    """

    @staticmethod
    def generate_otp(user_id: str, purpose: str = 'login') -> str:
        """
        Generates and stores an encrypted OTP (Synchronous).
        
        Args:
            user_id: The ID of the user (UUID safe).
            purpose: Context (login, reset, verify).
            
        Returns:
            str: The plain 6-digit code to send to the user.
        """
        try:
            # 1. Generate Secure Random Number
            otp_str = generate_numeric_otp(6)

            # 2. Encrypt
            encrypted_otp = encrypt_otp(otp_str)

            # 3. Store in Redis
            redis_client = get_redis_connection_safe()
            if not redis_client:
                 raise Exception("Redis unavailable for OTP storage.")
            
            key = f"otp:{user_id}:{purpose}"
            redis_client.set(key, encrypted_otp, ex=300)  # 5 minutes expiry

            logger.info(f"🔐 OTP Generated for User {user_id} (Purpose: {purpose})")
            return otp_str
        except Exception as e:
            logger.error(f"❌ OTP Generation Failed: {str(e)}")
            raise Exception("Failed to generate OTP.")

    @staticmethod
    def verify_otp(user_id: str, otp: str, purpose: str = 'login') -> bool:
        """
        Verifies a provided OTP against the encrypted version in Redis (Synchronous).
        """
        try:
            redis_client = get_redis_connection_safe()
            if not redis_client:
                raise Exception("Redis unavailable for OTP verification.")

            key = f"otp:{user_id}:{purpose}"
            
            stored_data = redis_client.get(key)
            if not stored_data:
                logger.warning(f"⚠️ OTP Verification Failed: No key found for User {user_id}")
                return False

            # Decrypt and Compare
            decrypted_otp = decrypt_otp(stored_data.decode())
            
            if decrypted_otp == otp:
                redis_client.delete(key) # Prevent replay attacks
                logger.info(f"✅ OTP Verified Successfully for User {user_id}")
                return True
            
            logger.warning(f"⛔ OTP Mismatch for User {user_id}")
            return False
        except Exception as e:
            logger.error(f"❌ OTP Verification Error: {str(e)}")
            return False
