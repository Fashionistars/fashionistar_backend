# apps/common/utils.py
import time
import random
import logging
import base64
from django.conf import settings
from cryptography.fernet import Fernet
from django_redis import get_redis_connection
import cloudinary.uploader
import datetime

application_logger = logging.getLogger('application')

# Initialize Fernet cipher suite for OTP encryption/decryption
# Ensure SECRET_KEY is robust enough or has fallback layer logic here
base_key = settings.SECRET_KEY.encode()
base_key = base_key.ljust(32, b'\0')[:32]  # Pad or truncate to ensure 32 bytes
cipher_suite = Fernet(base64.urlsafe_b64encode(base_key))

# Retry settings for Redis connection
REDIS_MAX_RETRIES = 3
REDIS_RETRY_DELAY = 1  # seconds

def encrypt_otp(otp):
    """
    Encrypts the given OTP using Fernet.
    """
    try:
        return cipher_suite.encrypt(otp.encode()).decode()
    except Exception as e:
        application_logger.error(f"OTP encryption failed: {e}")
        raise

def decrypt_otp(encrypted_otp):
    """
    Decrypts the given encrypted OTP using Fernet.
    """
    try:
        return cipher_suite.decrypt(encrypted_otp.encode()).decode()
    except Exception as e:
        application_logger.error(f"OTP decryption failed: {e}")
        raise

def get_redis_connection_safe(max_retries=REDIS_MAX_RETRIES, retry_delay=REDIS_RETRY_DELAY):
    """
    Establishes a safe connection to Redis, logging errors and returning None if unavailable.
    Implements retry mechanism for transient Redis failures.
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

def generate_numeric_otp(length=6):
    """
    Generates a numeric OTP of the specified length.
    """
    return ''.join(random.choices('0123456789', k=length))

def get_otp_expiry_datetime():
    """
    Calculates the OTP expiry datetime.

    Returns:
        datetime: A datetime object representing the OTP expiry time.
    """
    # Use timezone.now() if naive handling is tricky, strictly use UTC or server time
    # User's code used simple time, but django.utils.timezone is better
    # Keeping mostly faithful to user logic but robust
    from django.utils import timezone
    return timezone.now() + datetime.timedelta(seconds=300)

def delete_cloudinary_asset(public_id, resource_type="image"):
    """
    Deletes an asset from Cloudinary.
    Args:
        public_id (str): The public ID of the asset to delete.
        resource_type (str): Type of resource (image, video, raw).
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
