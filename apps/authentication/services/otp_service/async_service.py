# apps/authentication/services/otp_service/async_service.py

import logging
import asyncio
from typing import Union
from .sync_service import SyncOTPService

logger = logging.getLogger('application')

class AsyncOTPService:
    """
    Asynchronous Service for OTP Verification.
    """

    @staticmethod
    async def verify_otp(user_id: Union[int, str], otp_input: Union[str, int], purpose: str = "activation") -> bool:
        """
        Async OTP Verification.
        Wraps synchronous Redis operations in a thread.
        
        Args:
            user_id (int|str): The User ID.
            otp_input (str|int): The OTP provided by user.
            purpose (str): Context of verification.
            
        Returns:
            bool: True if verified.
        """
        # Redis operations are blocking, so we offload to thread
        return await asyncio.to_thread(SyncOTPService.verify_otp, user_id, otp_input, purpose)
