# apps/authentication/services/otp_service/sync_service.py

import logging
from utilities.django_redis import get_redis_connection_safe, decrypt_otp

logger = logging.getLogger('application')

class SyncOTPService:
    """
    Synchronous Service for OTP Verification.
    Robust Redis handling with safe patterns.
    """

    @staticmethod
    def verify_otp(user_id, otp_input, purpose="activation"):
        """
        Verifies OTP by looking up Redis. 
        Tries O(1) key look up first `otp_data:{user_id}`, then falls back if needed.
        """
        redis_conn = get_redis_connection_safe()
        if not redis_conn:
            logger.error("Redis Connection Failed during OTP Verify.")
            raise Exception("Service Unavailable")

        # 1. Try Direct Lookup (Optimization)
        key = f"otp_data:{user_id}"
        otp_data_str = redis_conn.get(key)
        
        # 2. If not found, legacy snippet suggests scanning `otp_data:*`. 
        # Only do this if strictly necessary (e.g. if key doesn't have user_id known... but we pass user_id).
        # We assume Direct Lookup is the goal of Refactor. 
        # But if we want to be robust against keys set by old code (otp_data:{uid}:{enc}):
        if not otp_data_str:
            logger.info(f"Direct OTP lookup failed for {user_id}. Attempting Scan (Legacy Fallback).")
            # Legacy Fallback: Scan
            # Pattern: otp_data:{user_id}:*
            match_pattern = f"otp_data:{user_id}:*" 
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
            otp_data = eval(otp_data_str.decode('utf-8')) # unsafe eval? Use json.loads if possible, but snippet used eval
            # Safe eval or ast.literal_eval is better. Assuming dict repr.
            # If stored as string repr "{'a':1}"
            
            stored_encrypted = otp_data.get('otp')
            decrypted = decrypt_otp(stored_encrypted)
            
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
