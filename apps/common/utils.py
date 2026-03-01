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
    from django.utils import timezone
    return timezone.now() + datetime.timedelta(seconds=300)


def user_directory_path(instance, filename) -> str:
    """
    Generate an optimized, role-separated file path for a given user directory.
    Matches Cloudinary modern layout expectations, with full domain separation
    (Users, Products, Vendors, Categories, Brands) and RBAC accountability.
    """
    import time
    from django.core.exceptions import ValidationError

    try:
        user = None
        domain = 'other'

        # 1. Determine root domain based on the instance's class name
        model_name = instance.__class__.__name__.lower()
        if 'product' in model_name:
            domain = 'products'
        elif 'vendor' in model_name:
            domain = 'vendors'
        elif 'category' in model_name:
            domain = 'categories'
        elif 'brand' in model_name:
            domain = 'brands'
        elif 'user' in model_name or 'profile' in model_name:
            domain = 'users'

        # 2. Extract the associated user for accountability mapping
        if hasattr(instance, 'user') and instance.user:
            user = instance.user
        elif hasattr(instance, 'vendor') and hasattr(instance.vendor, 'user') and instance.vendor.user:
            user = instance.vendor.user
        elif hasattr(instance, 'product') and hasattr(instance.product, 'vendor') and hasattr(instance.product.vendor, 'user'):
            user = getattr(instance.product.vendor, 'user', None)

        # 3. Handle Role-Based Access Control Segregation
        role_folder = "general"
        if user and hasattr(user, 'role') and user.role:
            role = str(user.role).lower()
            if role in ['admin', 'staff', 'support', 'reviewer', 'assistant']:
                role_folder = 'internal_staff'
            elif role == 'vendor':
                role_folder = 'vendors'
            elif role == 'client':
                role_folder = 'clients'

        # 4. Construct a latency-friendly path structure
        ext = filename.split('.')[-1] if '.' in filename else ''
        safe_filename = f"{getattr(instance, 'pk', 'new')}_{int(time.time())}.{ext}" if ext else f"{getattr(instance, 'pk', 'new')}_{int(time.time())}"

        if user:
            return f"uploads/{role_folder}/{domain}/user_{user.id}/{safe_filename}"
        else:
            return f"uploads/system/{domain}/general/{safe_filename}"

    except Exception as e:
        raise ValidationError(f"Error generating optimized file path: {str(e)}")


# ============================================================================
# CLOUDINARY UTILITIES
# ============================================================================

def delete_cloudinary_asset(public_id: str, resource_type: str = "image") -> Optional[dict]:
    """
    Deletes an asset from Cloudinary synchronously.
    """
    try:
        if not public_id:
            return None
        result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        application_logger.info(f"Cloudinary asset {public_id} deletion result: {result}")
        return result
    except Exception as e:
        application_logger.error(f"Error deleting Cloudinary asset {public_id}: {e}")
        return None

def delete_cloudinary_asset_async(public_id: str, resource_type: str = "image"):
    """
    Dispatches a background Celery task to delete a Cloudinary asset.
    Makes file deletions transaction-atomic and completely non-blocking
    for the main event loop to reduce latency.
    """
    if not public_id:
        return

    from django.db import transaction
    from apps.common.tasks import delete_cloudinary_asset_task

    def _fire():
        try:
            delete_cloudinary_asset_task.apply_async(
                args=[public_id],
                kwargs={"resource_type": resource_type},
                retry=False,
                ignore_result=True
            )
        except Exception as e:
            application_logger.warning(f"Broker unavailable — fallback to sync delete for {public_id}. Error: {e}")
            delete_cloudinary_asset(public_id, resource_type)

    # Fire ONLY after DB transaction commits successfully
    transaction.on_commit(_fire)
