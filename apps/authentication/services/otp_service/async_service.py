# apps/authentication/services/otp_service/async_service.py

import logging
import asyncio
from .sync_service import SyncOTPService

logger = logging.getLogger('application')

class AsyncOTPService:
    """
    Asynchronous Service for OTP Verification.
    """

    @staticmethod
    async def verify_otp(user_id, otp_input, purpose="activation"):
        """
        Async OTP Verification.
        """
        # Redis operations are blocking, so we offload to thread
        return await asyncio.to_thread(SyncOTPService.verify_otp, user_id, otp_input, purpose)
