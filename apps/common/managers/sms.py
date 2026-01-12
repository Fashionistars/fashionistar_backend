import logging
import asyncio
from typing import Any
from django.conf import settings
from admin_backend.sms_backend import DatabaseConfiguredSMSBackend

# Initialize application logger for detailed tracking of SMS operations
Logger = logging.getLogger('application')


class SMSManagerError(Exception):
    """
    Custom Exception for SMS Manager.
    Raised when critical errors occur during SMS dispatch or backend initialization.
    """
    pass


class SMSManager:
    """
    Centralized SMS Manager for handling all SMS communications.
    
    Features:
    - Supports both Synchronous and Asynchronous execution (via asyncio.to_thread).
    - Dynamic Backend Selection (handled transparently by admin_backend.sms_backend.DatabaseConfiguredSMSBackend).
    - Robust Error Handling and Logging.
    
    This manager abstracts the complexity of SMS sending, providing a clean interface
    identical to the EmailManager structural pattern.
    """
    
    # Retry logic configuration (if implemented in future versions)
    max_attempts = 3 

    @classmethod
    def send_sms(cls, to: str, body: str) -> str:
        """
        Sends an SMS immediately (Synchronous/Blocking).
        
        This method instantiates the DatabaseConfiguredSMSBackend (which resolves the 
        active provider from the DB) and dispatches the message.
        
        Args:
            to (str): The recipient's phone number (E.164 format recommended).
            body (str): The body content of the SMS message.
            
        Returns:
            str: The Message SID (Twilio) or Status String (API Response) upon success.
            
        Raises:
            SMSManagerError: If the backend fails to initialize or send the message.
        """
        if not to or not body:
             raise SMSManagerError("Invalid Arguments: 'to' and 'body' are required.")

        try:
            # Initialize the Dynamic Backend
            # This mirrors the behavior of Django's get_connection used in EmailManager
            backend = DatabaseConfiguredSMSBackend()
            
            # Dispatch the generic 'send_messages' call
            # The backend handles the specific provider logic (Twilio/Termii/etc.)
            result = backend.send_messages(to=to, body=body)
            
            Logger.info(f"✅ SMS sent successfully to {to}. Result/ID: {result}")
            return result
            
        except Exception as error:
            Logger.error(f"❌ Error sending SMS to {to}: {error}", exc_info=True)
            raise SMSManagerError(f"Failed to send SMS to {to}: {error}") from error

    @classmethod
    async def asend_sms(cls, to: str, body: str) -> str:
        """
        Sends an SMS asynchronously (Non-Blocking).
        
        This method wraps the synchronous `send_sms` method in `asyncio.to_thread`.
        This is crucial for modern Async Django views, as standard HTTP requests (httpx/requests)
        in the sync path are IO-blocking. Using a separate thread prevents the Main Async 
        Event Loop from freezing while waiting for the SMS provider's response.
        
        Architectural Note:
        Even though some providers might support native async, we enforce this pattern
        to strictly align with the `EmailManager` architecture and ensure consistent
        parallel execution behavior.
        
        Args:
            to (str): The recipient's phone number.
            body (str): The body content of the SMS.
            
        Returns:
            str: The Message SID or Status String.
        """
        # Offload the blocking sync call to a worker thread
        # This implementation is Pyton/Django Future-Proof and ensures main thread non-blocking.
        return await asyncio.to_thread(
            cls.send_sms,
            to=to,
            body=body
        )
