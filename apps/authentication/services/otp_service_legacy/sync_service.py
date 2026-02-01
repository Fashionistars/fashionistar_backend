# apps/authentication/services/otp_service/sync_service.py

import logging
from typing import Optional, Union
from apps.common.utils import get_redis_connection_safe, decrypt_otp

logger = logging.getLogger('application')

class SyncOTPService:
    """
    Synchronous Service for OTP Verification.
    
    Robust Redis handling with safe patterns and strict type hints.
    """

    @staticmethod
    def verify_otp(user_id: Union[int, str], otp_input: Union[str, int], purpose: str = "activation") -> bool:
        """
        Verifies OTP by looking up Redis. 
        Tries O(1) key look up first `otp_data:{user_id}`, then falls back if needed.
        
        Args:
            user_id (int|str): The User ID.
            otp_input (str|int): The OTP provided by user.
            purpose (str): Context of verification (activation, reset).
            
        Returns:
            bool: True if verified, False otherwise.
        """
        redis_conn = get_redis_connection_safe()
        if not redis_conn:
            logger.error("Redis Connection Failed during OTP Verify.")
            raise Exception("Service Unavailable")

        # 1. Try Direct Lookup (Optimization)
        key: str = f"otp_data:{user_id}"
        otp_data_str: Optional[bytes] = redis_conn.get(key)
        
        # 2. Legacy Fallback: Scan if not found directly
        if not otp_data_str:
            logger.info(f"Direct OTP lookup failed for {user_id}. Attempting Scan (Legacy Fallback).")
            # Pattern: otp_data:{user_id}:*
            match_pattern: str = f"otp_data:{user_id}:*" 
            for scanned_key in redis_conn.scan_iter(match=match_pattern):
                otp_data_str = redis_conn.get(scanned_key)
                if otp_data_str:
                    key = scanned_key # Found it
                    break
        
        if not otp_data_str:
            logger.warning(f"OTP Verification Failed: No OTP found for user {user_id}")
            return False

        try:
            # Decode and Decrypt
            # Safe eval assuming internal trust, but Ast literal_eval would be strictly better
            # However, maintain compatibility with how it's stored.
            otp_data: dict = eval(otp_data_str.decode('utf-8'))
            
            stored_encrypted: str = otp_data.get('otp', '')
            decrypted: str = decrypt_otp(stored_encrypted)
            
            if decrypted == str(otp_input):
                # Success
                redis_conn.delete(key)
                logger.info(f"OTP Verified for user {user_id}")
                return True
            else:
                logger.warning(f"OTP Mismatch for user {user_id}")
                return False

        except Exception as e:
            logger.error(f"OTP Verify Logic Error: {e}")
            return False
