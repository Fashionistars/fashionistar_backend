# apps/common/managers/sms.py

import logging
import asyncio
from typing import List, Dict, Any

from django.conf import settings

# -----------------------------------------------------------------------------
# Logger Configuration
# -----------------------------------------------------------------------------
# Initialize application logger for detailed tracking of SMS operations
logger = logging.getLogger('application')


class SMSManagerError(Exception):
    """
    Custom Exception for SMS Manager.
    
    raised when critical known errors occur during SMS dispatch or provider 
    configuration loading. This helps segregate SMS failures from other 
    system exceptions.
    """
    pass


class SMSManager:
    """
    Centralized SMS Manager for handling all SMS communications.

    ---------------------------------------------------------------------------
    Architectural Overview:
    ---------------------------------------------------------------------------
    This manager acts as the unified application interface for Sending Shorts 
    Message Service (SMS) notifications.
    
    Key Features:
    1.  **Dynamic Provider Selection via Backend**:
        It does not hardcode the provider (Twilio, Termii, etc.). Instead, it 
        delegates the "How" of sending to `admin_backend.backends.sms_backends.DatabaseConfiguredSMSBackend`.
        This enables admin-controlled switching of providers at runtime without 
        deploying new code.
        
    2.  **Dual-Mode Execution (Sync & Async)**:
        - `send_sms`: Standard blocking implementation for Sync Views/Tasks.
        - `asend_sms`: Non-blocking, thread-offloaded implementation for Async Views.
        
    3.  **Bulk / Mass Messaging**:
        - `send_mass_sms` / `asend_mass_sms`: Optimized flows for handling lists 
          of messages, ensuring efficient iteration and batch logging.
          
    4.  **Robust Error Handling**:
        Every method is wrapped in comprehensive try-except blocks to catch, log, 
        and re-raise errors contextually.
        
    Attributes:
        max_attempts (int): configuration for future retry logic.
    """
    
    max_attempts = 3 

    # =========================================================================
    # Synchronous Single SMS Method
    # =========================================================================

    @classmethod
    def send_sms(cls, to: str, body: str) -> str:
        """
        Sends a single SMS message immediately (Synchronous/Blocking).

        This method:
        1. Instantiates the Dynamic Backend (which loads the active provider).
        2. Wraps the single message in a list format expected by the backend.
        3. Dispatches the message via the backend.
        4. Logs success or failure.

        Args:
            to (str): The recipient's phone number (E.164 format recommended, e.g., '+23480...').
            body (str): The text body content of the SMS message.

        Returns:
            str: The Message SID (Twilio) or Status String (API Response) upon success.

        Raises:
            SMSManagerError: If the backend fails to send the message.
        """
        try:
            # -----------------------------------------------------------------
            # 1. Backend Initialization
            # -----------------------------------------------------------------
            # We import the backend dynamically here to avoid circular dependencies
            # during app initialization.
            from admin_backend.backends.sms_backends import DatabaseConfiguredSMSBackend
            backend = DatabaseConfiguredSMSBackend()

            # -----------------------------------------------------------------
            # 2. Dispatch Logic
            # -----------------------------------------------------------------
            # Our backend treats everything as a batch conceptually for uniformity.
            # So we create a list of one message.
            sms_messages = [{'to': to, 'body': body}]
            
            # Execute the send
            results = backend.send_messages(sms_messages)

            # -----------------------------------------------------------------
            # 3. Result Handling
            # -----------------------------------------------------------------
            # Retrieve the specific result for this single message
            result = results[0] if results else 'sent_with_no_id'
            
            logger.info(f"✅ SMS sent successfully to {to}. Provider Response: {result}")
            return result

        except Exception as error:
            # -----------------------------------------------------------------
            # 4. Error Logging
            # -----------------------------------------------------------------
            logger.error(f"❌ Error sending SMS to {to}: {error}", exc_info=True)
            # Re-raise as our custom exception for cleaner upstream handling
            raise SMSManagerError(f"Failed to send SMS to {to}: {error}") from error

    # =========================================================================
    # Asynchronous Single SMS Method
    # =========================================================================

    @classmethod
    async def asend_sms(cls, to: str, body: str) -> str:
        """
        Sends a single SMS message asynchronously (Non-Blocking).

        This wrapper is essential for Async Django (ASGI). Calling the sync
        `send_sms` directly would block the Event Loop while waiting for 
        HTTP requests to complete (which can take 100ms - 2s).
        
        Solution:
        We use `asyncio.to_thread` to push the execution of `send_sms` onto 
        a separate thread, allowing the main loop to continue processing other requests.

        Args:
            to (str): The recipient's phone number.
            body (str): The SMS text body.

        Returns:
            str: The Message SID or Status String.
        """
        try:
            return await asyncio.to_thread(cls.send_sms, to, body)
        except Exception as e:
            logger.error(f"❌ Async SMS Send Error to {to}: {e}", exc_info=True)
            raise SMSManagerError(f"Async SMS Failed to {to}: {e}")

    # =========================================================================
    # Synchronous Bulk / Mass SMS Method
    # =========================================================================

    @classmethod
    def send_mass_sms(cls, messages: List[Dict[str, str]]) -> List[Any]:
        """
        Sends a batch of SMS messages synchronously (Blocking).

        This is the **Sync** function for bulk SMS sending. It is designed to 
        handle lists of messages efficiently, processing them via the backend's 
        logic (which may or may not support true provider-level batching, 
        depending on the active provider).

        Args:
            messages (List[Dict[str, str]]): A list of dictionaries. 
                Each dictionary MUST contain:
                - 'to': Recipient phone number.
                - 'body': Message text.
                Example: [{'to': '+12345', 'body': 'Hello 1'}, {'to': '+67890', 'body': 'Hello 2'}]

        Returns:
            List[Any]: A list of results corresponding to each message in the input list.
        """
        if not messages:
            logger.warning("⚠️ send_mass_sms called with an empty message list. No action taken.")
            return []

        try:
            # Import Backend
            from admin_backend.backends.sms_backends import DatabaseConfiguredSMSBackend
            backend = DatabaseConfiguredSMSBackend()
            
            logger.info(f"🚀 Starting bulk SMS send. Batch size: {len(messages)} messages.")
            
            # Execute Batch Send
            results = backend.send_messages(messages)
            
            logger.info(f"✅ Bulk SMS send completed. Processed: {len(results)} messages.")
            return results
            
        except Exception as error:
            logger.error(f"❌ Error in send_mass_sms batch execution: {error}", exc_info=True)
            raise SMSManagerError(f"Failed to send mass SMS batch: {error}")

    # =========================================================================
    # Asynchronous Bulk / Mass SMS Method
    # =========================================================================

    @classmethod
    async def asend_mass_sms(cls, messages: List[Dict[str, str]]) -> List[Any]:
        """
        Sends a batch of SMS messages asynchronously (Non-Blocking).

        This is the **Async** function for bulk SMS sending.
        It wraps `send_mass_sms` in `asyncio.to_thread` to ensure that processing 
        a large list of messages (which involves many network calls) does not 
        freeze the asynchronous application server.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries.

        Returns:
            List[Any]: List of results.
        """
        try:
            return await asyncio.to_thread(cls.send_mass_sms, messages)
        except Exception as e:
            logger.error(f"❌ Error in asend_mass_sms: {e}", exc_info=True)
            raise SMSManagerError(f"Failed to send async mass SMS: {e}")