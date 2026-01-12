import logging
import importlib
from django.apps import apps
from django.conf import settings
from django.utils.module_loading import import_string

# Initialize application logger for detailed tracking of SMS backend operations
application_logger = logging.getLogger('application')

class DatabaseConfiguredSMSBackend:
    """
    Database Configured SMS Backend.

    This backend serves as a centralized gateway for dispatching SMS messages.
    It dynamically selects and instantiates the active SMS provider strategy
    configured in the `admin_backend.SMSBackendConfig` model.

    Architectural Alignment:
    - This class mirrors the design of `admin_backend.backends.DatabaseConfiguredEmailBackend`.
    - It decouples the core application logic from specific SMS providers (Twilio, Termii, etc.).
    - It ensures that the provider choice is runtime-configurable via the Admin Panel.
    """

    def __init__(self, *args, **kwargs):
        """
        Initializes the SMS Backend.

        Process:
        1. Attempts to retrieve the active `SMSBackendConfig` from the database.
        2. If found, uses the configured python path to the provider class.
        3. If not found (or on error), falls back to a default provider (Twilio).
        4. Dynamically imports and instantiates the provider class.
        """
        self.sms_provider = None
        self.provider_path = None

        try:
            # Dynamically retrieval of the configuration model to avoid circular imports
            try:
                SMSBackendConfig = apps.get_model('admin_backend', 'SMSBackendConfig')
                config = SMSBackendConfig.objects.first()
            except LookupError:
                # Fallback if migration hasn't run yet or app not ready
                application_logger.warning("⚠️ Admin Backend app not ready or model not found. Using default SMS provider.")
                config = None

            if config:
                self.provider_path = config.sms_backend
                application_logger.info(f"✅ Loaded SMS Provider Configuration from Database: {self.provider_path}")
            else:
                # Default Fallback Provider
                self.provider_path = 'apps.common.providers.SMS.twilio.TwilioSMSProvider'
                application_logger.warning("⚠️ No active SMSBackendConfig found. Defaulting to TwilioSMSProvider.")

            # Dynamic Import Logic
            # We use Django's import_string or standard importlib to load the class
            try:
                provider_class = import_string(self.provider_path)
                self.sms_provider = provider_class(*args, **kwargs)
                application_logger.info(f"🚀 Successfully instantiated SMS Provider: {provider_class.__name__}")
            except ImportError as import_err:
                application_logger.error(f"❌ Failed to import SMS provider '{self.provider_path}': {import_err}", exc_info=True)
                raise import_err

        except Exception as e:
            application_logger.error(f"❌ Critical Error initializing SMS backend: {e}", exc_info=True)
            # Robust Fallback to Twilio in case of total failure
            self.provider_path = 'apps.common.providers.SMS.twilio.TwilioSMSProvider'
            from apps.common.providers.SMS.twilio import TwilioSMSProvider
            self.sms_provider = TwilioSMSProvider(*args, **kwargs)
            application_logger.info("🔄 Fallback to TwilioSMSProvider activated due to initialization error.")

    def send_messages(self, to: str, body: str) -> str:
        """
        Dispatches the SMS message using the instantiated provider.

        This method acts as a proxy, delegating the actual sending logic to the
        underlying provider instance (e.g., TwilioSMSProvider.send()).

        Args:
            to (str): The recipient's phone number.
            body (str): The text content of the SMS.

        Returns:
            str: The result from the provider (usually Message SID or ID).
        """
        if not self.sms_provider:
            application_logger.error("❌ No SMS Provider instantiated. Cannot send message.")
            raise RuntimeError("SMS Backend not initialized properly.")

        return self.sms_provider.send(to, body)
