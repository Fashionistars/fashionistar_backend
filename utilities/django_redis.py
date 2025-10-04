# utilities/django_redis
import time
import random
from django.conf import settings
from cryptography.fernet import Fernet
import base64

from django_redis import get_redis_connection


import logging

application_logger = logging.getLogger('application')

# Initialize Fernet cipher suite for OTP encryption/decryption
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
    import time
    import datetime
    timestamp = time.time() + 300
    dt_object = datetime.datetime.fromtimestamp(timestamp)
    dt_object += datetime.timedelta()
    return dt_object







