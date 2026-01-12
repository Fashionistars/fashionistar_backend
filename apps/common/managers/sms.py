import logging
import asyncio
from django.conf import settings
from django.apps import apps
from django.utils.module_loading import import_string

# Get a logger instance for this module or the application
application_logger = logging.getLogger('application')

class SMSManagerError(Exception):
    """
    Custom exception for SMS Manager related errors.
    Raised when SMS sending fails or provider configuration is invalid.
    """
    pass

class SMSManager:
    """
    Manages the sending of SMS messages using dynamically selected providers.
    
    This manager handles the logic for selecting the active SMS provider configured
    in the admin backend and dispatching the message. It supports both synchronous
    execution (blocking) and asynchronous execution (non-blocking) via `asyncio.to_thread`.
    
    The `_get_provider` method uses Django's `import_string` utility to dynamically
    load the provider class path stored in the database, offering extreme flexibility.
    """

    @classmethod
    def _get_provider(cls):
        """
        Dynamically retrieves and instantiates the active SMS provider class.
        
        This method queries the `SMSBackendConfig` model (from `admin_backend`) to find
        the currently selected provider path (e.g., 'apps.common.providers.SMS.twilio.TwilioSMSProvider').
        It then dynamically imports and initializes this class.
        
        Returns:
            object: An instance of the selected SMS provider class.
        
        Fallback:
            If no configuration exists or dynamic import fails, it defaults to the
            `TwilioSMSProvider` to ensure the system remains operational.
        """
        try:
            # Dynamically get the model to avoid top-level circular imports if any
            SMSBackendConfig = apps.get_model('admin_backend', 'SMSBackendConfig')
            config = SMSBackendConfig.objects.first()
            
            if config:
                provider_path = config.sms_backend
                application_logger.info(f"Loading SMS Provider from configuration: {provider_path}")
            else:
                provider_path = 'apps.common.providers.SMS.twilio.TwilioSMSProvider'
                application_logger.warning("No SMSBackendConfig found. Defaulting to TwilioSMSProvider.")
            
            # Use Django's utility to import the class from the string path
            provider_class = import_string(provider_path)
            return provider_class()
            
        except Exception as e:
            application_logger.error(f"Critical Error loading SMS provider: {e}", exc_info=True)
            # Fallback hardcoded if everything else fails
            from apps.common.providers.SMS.twilio import TwilioSMSProvider
            return TwilioSMSProvider()

    @classmethod
    def send_sms(cls, to: str, body: str) -> str:
        """
        Sends an SMS message synchronously (blocking).
        
        This method retrieves the active provider and calls its `send_sms` method.
        It wraps the call in a try-except block to log errors and re-raise a custom exception.
        
        Args:
            to (str): The recipient's phone number (E.164 format recommended).
            body (str): The body content of the SMS message.
            
        Returns:
            str: The Message SID (Twilio) or Status String (API Response) upon success.
            
        Raises:
            SMSManagerError: If the provider fails to send the message.
        """
        try:
            provider = cls._get_provider()
            sid = provider.send_sms(to, body)
            application_logger.info(f"SMS sent successfully to {to} via {provider.__class__.__name__}. ID/SID: {sid}")
            return sid
        except Exception as error:
            application_logger.error(f"Failed to send SMS to {to}: {error}", exc_info=True)
            raise SMSManagerError(f"Failed to send SMS to {to}: {error}")

    @classmethod
    async def asend_sms(cls, to: str, body: str) -> str:
        """
        Sends an SMS message asynchronously (non-blocking).
        
        This wrapper is designed for use in Async Views and Consumers. It offloads
        the blocking I/O operation (the HTTP request in `send_sms`) to a separate thread
        using `asyncio.to_thread`. This ensures that the main Async Event Loop is NEVER blocked,
        providing high performance and responsiveness.
        
        Args:
            to (str): The recipient's phone number.
            body (str): The body content of the SMS.
            
        Returns:
            str: The Message SID or Status String.
        """
        try:
            # asyncio.to_thread runs the synchronous function in a separate thread
            return await asyncio.to_thread(cls.send_sms, to, body)
        except Exception as e:
            # We catch it here to ensure any thread-boundary errors are logged with context
            application_logger.error(f"Async SMS Send Error to {to}: {e}", exc_info=True)
            raise SMSManagerError(f"Async SMS Failed to {to}: {e}")
