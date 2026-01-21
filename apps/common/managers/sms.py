# apps/common/managers/sms.py

import logging
import asyncio
from typing import List
from django.conf import settings

# Initialize application logger for detailed tracking of SMS operations
logger = logging.getLogger('application')

class SMSManagerError(Exception):
    """
    Custom Exception for SMS Manager.
    Raised when critical errors occur during SMS dispatch or provider configuration.
    """
    pass

class SMSManager:
    """
    Centralized SMS Manager for handling all SMS communications.

    Features:
    - Supports both Synchronous and Asynchronous execution (via asyncio.to_thread).
    - Dynamic Provider Selection (handled transparently by admin_backend's DatabaseConfiguredSMSBackend).
    - Robust Error Handling and Logging for production reliability.
    - Unified Interface for sending SMS messages across different providers.

    This manager abstracts the complexity of SMS sending, providing a clean interface
    for the rest of the application. It leverages the DatabaseConfiguredSMSBackend for
    dynamic provider selection based on admin configurations.
    """

    @classmethod
    def send_sms(cls, to: str, body: str) -> str:
        """
        Sends an SMS message immediately (Synchronous/Blocking).

        This method constructs an SMS message and dispatches it using the configured backend.
        It wraps the call in a try-except block to log errors and re-raise a custom exception.

        Args:
            to (str): The recipient's phone number (E.164 format recommended).
            body (str): The body content of the SMS message.

        Returns:
            str: The Message SID (Twilio) or Status String (API Response) upon success.

        Raises:
            SMSManagerError: If the backend fails to send the message.
        """
        try:
            # Import the backend dynamically to avoid circular imports
            from admin_backend.backends.sms_backends import DatabaseConfiguredSMSBackend
            backend = DatabaseConfiguredSMSBackend()

            # Prepare the message in the expected format
            sms_messages = [{'to': to, 'body': body}]
            results = backend.send_messages(sms_messages)

            # Return the result for the single message
            result = results[0] if results else 'sent'
            logger.info(f"✅ SMS sent successfully to {to}")
            return result

        except Exception as error:
            logger.error(f"❌ Error sending SMS to {to}: {error}", exc_info=True)
            raise SMSManagerError(f"Failed to send SMS to {to}: {error}")

    @classmethod
    async def asend_sms(cls, to: str, body: str) -> str:
        """
        Sends an SMS message asynchronously (Non-Blocking).

        This method wraps the synchronous `send_sms` method in `asyncio.to_thread`.
        This is crucial for modern Async Django views, as SMS operations involve I/O-blocking
        HTTP requests to third-party providers. Using a separate thread prevents the Main Async
        Event Loop from freezing while waiting for the provider's response.

        Args:
            Same as send_sms.

        Returns:
            str: The Message SID or Status String.
        """
        try:
            # Offload the blocking sync call to a worker thread
            return await asyncio.to_thread(cls.send_sms, to, body)
        except Exception as e:
            # We catch it here to ensure any thread-boundary errors are logged with context
            logger.error(f"❌ Async SMS Send Error to {to}: {e}", exc_info=True)
            raise SMSManagerError(f"Async SMS Failed to {to}: {e}")

    @classmethod
    def bulk_send_sms(cls, sms_messages: List[dict[str, str]]) -> List[str]:
        """
        Sends multiple SMS messages in bulk (Synchronous/Blocking).

        This method processes a list of SMS message dictionaries, dispatching each one
        using the configured backend. It returns a list of message IDs or status strings.

        Args:
            sms_messages (List[dict[str, str]]): A list of dictionaries, each containing:
                - 'to' (str): The recipient's phone number (E.164 format recommended).
                - 'body' (str): The text content of the SMS message.

        Returns:
            List[str]: A list of Message SIDs or Status Strings for each sent message.

        Raises:
            SMSManagerError: If any message fails to send or validation fails.
        """
        try:
            results = []
            for sms_data in sms_messages:
                to = sms_data.get('to')
                body = sms_data.get('body')

                # Validate required fields
                if not to or not body:
                    raise SMSManagerError("Each SMS message must have 'to' and 'body'.")

                # Send individual SMS
                result = cls.send_sms(to=to, body=body)
                results.append(result)

            logger.info(f"✅ Bulk SMS sending completed: {len(results)} messages sent.")
            return results

        except Exception as e:
            logger.error(f"❌ Error in bulk SMS sending: {e}", exc_info=True)
            raise SMSManagerError(f"Bulk SMS sending failed: {e}")

    @classmethod
    async def abulk_send_sms(cls, sms_messages: List[dict[str, str]]) -> List[str]:
        """
        Sends multiple SMS messages in bulk asynchronously (Non-Blocking).

        This method wraps the synchronous bulk_send_sms in asyncio.to_thread to prevent
        blocking the event loop during batch SMS operations.

        Args:
            sms_messages (List[dict[str, str]]): Same as bulk_send_sms.

        Returns:
            List[str]: Same as bulk_send_sms.
        """
        try:
            # Offload the blocking bulk operation to a worker thread
            return await asyncio.to_thread(cls.bulk_send_sms, sms_messages)
        except Exception as e:
            logger.error(f"❌ Error in async bulk SMS sending: {e}", exc_info=True)
            raise SMSManagerError(f"Async bulk SMS sending failed: {e}")
