# apps/common/utils.py
import time
import random
import logging
import base64
import datetime
from typing import Optional, Any
from django.conf import settings
from cryptography.fernet import Fernet
from django_redis import get_redis_connection
import cloudinary.uploader
from django.utils import timezone

application_logger = logging.getLogger('application')

# ============================================================================
# INITIALIZATION
# ============================================================================

# Initialize Fernet cipher suite for OTP encryption/decryption
try:
    base_key = settings.SECRET_KEY.encode()
    # Pad or truncate to ensure 32 bytes for Fernet
    base_key = base_key.ljust(32, b'\0')[:32]
    cipher_suite = Fernet(base64.urlsafe_b64encode(base_key))
except Exception as e:
    application_logger.critical(f"Failed to initialize encryption key: {e}")
    cipher_suite = None

# Retry settings for Redis connection
REDIS_MAX_RETRIES: int = 3
REDIS_RETRY_DELAY: int = 1  # seconds


# ============================================================================
# CRYPTOGRAPHY UTLITIES
# ============================================================================

def encrypt_otp(otp: str) -> str:
    """
    Encrypts the given OTP using Fernet.
    
    Args:
        otp (str): The plain text OTP.
        
    Returns:
        str: Encrypted OTP string.

    Raises:
        RuntimeError: If encryption suite is not initialized.
    """
    if not cipher_suite:
         raise RuntimeError("Encryption suite not initialized")
    try:
        return cipher_suite.encrypt(otp.encode()).decode()
    except Exception as e:
        application_logger.error(f"OTP encryption failed: {e}")
        raise

def decrypt_otp(encrypted_otp: str) -> str:
    """
    Decrypts the given encrypted OTP using Fernet.

    Args:
        encrypted_otp (str): The encrypted OTP string.

    Returns:
        str: Decrypted OTP string.

    Raises:
        RuntimeError: If encryption suite is not initialized.
    """
    if not cipher_suite:
         raise RuntimeError("Encryption suite not initialized")
    try:
        return cipher_suite.decrypt(encrypted_otp.encode()).decode()
    except Exception as e:
        application_logger.error(f"OTP decryption failed: {e}")
        raise


# ============================================================================
# REDIS UTILITIES
# ============================================================================

def get_redis_connection_safe(max_retries: int = REDIS_MAX_RETRIES, retry_delay: int = REDIS_RETRY_DELAY) -> Optional[Any]:
    """
    Establishes a safe connection to Redis with retry mechanism.

    Args:
        max_retries (int): Number of connection attempts.
        retry_delay (int): Seconds to wait between retries.

    Returns:
        redis.StrictRedis or None: Active Redis connection or None if failed.
    """
    for attempt in range(max_retries):
        try:
            redis_conn = get_redis_connection("default")
            redis_conn.ping()  # Ensure Redis is available
            return redis_conn
        except Exception as e:
            application_logger.error(f"Redis connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)  # Wait before retrying
            else:
                application_logger.error("Max Redis connection retries reached. Redis unavailable.")
                return None
    return None


# ============================================================================
# GENERATION UTILITIES
# ============================================================================

def generate_numeric_otp(length: int = 6) -> str:
    """
    Generates a numeric OTP of the specified length.
    
    Args:
        length (int): Length of OTP.
        
    Returns:
        str: Numeric OTP string.
    """
    return ''.join(random.choices('0123456789', k=length))


def get_otp_expiry_datetime() -> datetime.datetime:
    """
    Calculates the OTP expiry datetime (5 minutes from now).

    Returns:
        datetime: A timezone-aware datetime object representing the expiry time.
    """
    # Use timezone.now() if naive handling is tricky, strictly use UTC or server time
    # User's code used simple time, but django.utils.timezone is better
    # Keeping mostly faithful to user logic but robust
    from django.utils import timezone
    return timezone.now() + datetime.timedelta(seconds=300)


# ============================================================================
# CLOUDINARY UTILITIES
# ============================================================================

def delete_cloudinary_asset(public_id: str, resource_type: str = "image") -> Optional[dict]:
    """
    Deletes an asset from Cloudinary.

    Args:
        public_id (str): The public ID of the asset.
        resource_type (str): Type of resource (image, video, raw).

    Returns:
        dict or None: Result of deletion or None if failed.
    """
    try:
        if not public_id:
            return None
        # Remove version if present (not strictly needed for destroy, but good practice if URL is passed)
        # Assuming public_id is passed directly.
        
        result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        application_logger.info(f"Cloudinary asset {public_id} deletion result: {result}")
        return result
    except Exception as e:
        application_logger.error(f"Error deleting Cloudinary asset {public_id}: {e}")
        return None
