import logging
import datetime
from typing import Dict, Any, Optional
from asgiref.sync import sync_to_async
from apps.common.utils import (
    get_redis_connection_safe,
    generate_numeric_otp,
    encrypt_otp,
    decrypt_otp,
    get_otp_expiry_datetime
)

logger = logging.getLogger('application')

class OTPService:
    """
    Centralized OTP Management Service.
    Handles Generation, Storage (Redis), Encryption, and Verification.
    Supports both Synchronous and Asynchronous execution.
    """

    @staticmethod
    def generate_otp_sync(user_id: int, purpose: str = 'verify') -> str:
        """
        Generates, Encrypts, and Stores an OTP in Redis (Synchronous).
        
        Args:
            user_id (int): The user ID.
            purpose (str): Purpose of OTP (verify, reset, login).
            
        Returns:
            str: The plain-text OTP (to be sent via Email/SMS).
            
        Raises:
            Exception: If Redis is unavailable.
        """
        try:
            # 1. Generate numeric OTP
            otp = generate_numeric_otp()
            
            # 2. Encrypt OTP
            encrypted_otp = encrypt_otp(otp)
            
            # 3. Store in Redis
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                logger.error(f"Redis unavailable for OTP generation (User: {user_id})")
                raise Exception("Service unavailable")
            
            # Key Pattern: otp:{user_id}:{purpose}:{encrypted_otp_snippet}
            # Actually, to verify we need to look it up.
            # The plan suggests: redis_key = f"otp:{user_id}:{purpose}:{encrypted_otp[:8]}"
            # But wait, if we key by encrypted OTP snippet, we can't find it easily unless we scan.
            # The plan says "Scan for matching OTP key using scan_iter".
            # So the key must contain the user_id and purpose to allow scanning `otp:{user_id}:{purpose}:*`.
            
            # We'll use the encrypted OTP as part of the key to ensure uniqueness 
            # and to allow 'stateless' verification if we wanted, 
            # but mainly to avoid collisions.
            # However, we store the full encrypted OTP as the value?
            # The plan says: "Store encrypted OTP in Redis with user_id in key".
            # Plan Code Snippet: redis_key = f"otp:{user_id}:{purpose}:{encrypted_otp[:8]}"
            # Value: encrypted_otp (full) or just '1'?
            # If we store encrypted OTP in the value, we can verify it.
            
            # Let's stick to the plan's key pattern.
            snippet = encrypted_otp[:16] # Use slightly longer snippet for safety
            redis_key = f"otp:{user_id}:{purpose}:{snippet}"
            
            # Store the full encrypted OTP in the value, just in case we need it, 
            # OR just '1' if the key itself implies validity. 
            # But the verify logic "Decrypts stored OTP". 
            # This implies the VALUE in Redis is the encrypted OTP usually?
            # "Scan Redis... Decrypt stored OTP... Compare"
            # So yes, we should store the encrypted OTP in the value.
            
            redis_conn.setex(redis_key, 300, encrypted_otp) # 5 minutes TTL
            
            logger.info(f"OTP generated for User {user_id} (Purpose: {purpose})")
            return otp
            
        except Exception as e:
            logger.error(f"OTP Generation Failed: {e}", exc_info=True)
            raise

    @staticmethod
    async def generate_otp_async(user_id: int, purpose: str = 'verify') -> str:
        """
        Generates, Encrypts, and Stores an OTP in Redis (Asynchronous).
        """
        # Since django-redis and cryptography are synchronous CPU/Network bound,
        # we wrap the sync method in sync_to_async for NON-BLOCKING execution.
        return await sync_to_async(OTPService.generate_otp_sync)(user_id, purpose)

    @staticmethod
    def verify_otp_sync(user_id: int, otp: str, purpose: str = 'verify') -> bool:
        """
        Verifies an OTP (Synchronous).
        Scans Redis for keys matching otp:{user_id}:{purpose}:*
        Decrypts values and compares.
        Deletes on success (One-Time Use).
        """
        try:
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                raise Exception("Service unavailable")

            pattern = f"otp:{user_id}:{purpose}:*"
            # Returns generator of binary keys
            keys = redis_conn.keys(pattern) 
            
            for key in keys:
                stored_encrypted_val = redis_conn.get(key)
                if not stored_encrypted_val:
                    continue
                    
                decrypted = decrypt_otp(stored_encrypted_val.decode())
                
                if decrypted == otp:
                    # Match found!
                    redis_conn.delete(key)
                    logger.info(f"OTP Verified for User {user_id} (Purpose: {purpose})")
                    return True
            
            logger.warning(f"OTP Verification Failed for User {user_id} (Purpose: {purpose})")
            return False

        except Exception as e:
            logger.error(f"OTP Verification Error: {e}", exc_info=True)
            return False

    @staticmethod
    async def verify_otp_async(user_id: int, otp: str, purpose: str = 'verify') -> bool:
        """
        Verifies an OTP (Asynchronous).
        """
        return await sync_to_async(OTPService.verify_otp_sync)(user_id, otp, purpose)
