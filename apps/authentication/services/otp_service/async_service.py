# apps/authentication/services/otp_service/async_service.py

import logging
import asyncio
from typing import Optional
from .sync_service import SyncOTPService

logger = logging.getLogger('application')

class AsyncOTPService:
    """
    Asynchronous Service for handling One-Time Passwords (OTP).
    Wraps synchronous Redis operations in threads to prevent event loop blocking.
    """

    @staticmethod
    async def generate_otp(user_id: str, purpose: str = 'login') -> str:
        """
        Generates and stores an encrypted OTP (Asynchronous).
        """
        try:
            return await asyncio.to_thread(
                SyncOTPService.generate_otp,
                user_id,
                purpose
            )
        except Exception as e:
            logger.error(f"❌ Async OTP Generation Error: {str(e)}")
            raise

    @staticmethod
    async def verify_otp(user_id: str, otp: str, purpose: str = 'login') -> bool:
        """
        Verifies a provided OTP against the encrypted version in Redis (Asynchronous).
        """
        try:
            return await asyncio.to_thread(
                SyncOTPService.verify_otp,
                user_id,
                otp,
                purpose
            )
        except Exception as e:
            logger.error(f"❌ Async OTP Verification Error: {str(e)}")
            return False
