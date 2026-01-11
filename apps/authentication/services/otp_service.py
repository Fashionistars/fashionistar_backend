import secrets
import redis
from django.conf import settings
from apps.common.utils import encrypt_otp, decrypt_otp
import logging

logger = logging.getLogger('application')

class OTPService:
    """
    Service for handling One-Time Passwords (OTP).
    - Generates 6-digit numeric codes.
    - Encrypts codes before storage.
    - Stores in Redis with TTL (Time To Live).
    """

    @staticmethod
    def generate_otp(user_id: int, purpose: str = 'login') -> str:
        """
        Generates and stores an encrypted OTP.
        
        Args:
            user_id: The ID of the user.
            purpose: Context (login, reset, verify).
            
        Returns:
            str: The plain 6-digit code to send to the user.
        """
        try:
            # 1. Generate Secure Random Number
            otp_code = secrets.randbelow(1000000)
            otp_str = f"{otp_code:06d}"

            # 2. Encrypt
            encrypted_otp = encrypt_otp(otp_str)

            # 3. Store in Redis
            redis_client = redis.Redis.from_url(settings.REDIS_URL)
            key = f"otp:{user_id}:{purpose}"
            redis_client.set(key, encrypted_otp, ex=300)  # 5 minutes expiry

            logger.info(f"🔐 OTP Generated for User {user_id} (Purpose: {purpose})")
            return otp_str
        except Exception as e:
            logger.error(f"❌ OTP Generation Failed: {str(e)}")
            raise Exception("Failed to generate OTP.")

    @staticmethod
    def verify_otp(user_id: int, otp: str, purpose: str = 'login') -> bool:
        """
        Verifies a provided OTP against the encrypted version in Redis.
        """
        try:
            redis_client = redis.Redis.from_url(settings.REDIS_URL)
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
