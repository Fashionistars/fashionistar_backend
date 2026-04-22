# admin_backend/backends/sms_backends.py

import logging
from django.apps import apps
from django.conf import settings
from django.utils.module_loading import import_string

# -----------------------------------------------------------------------------
# Logger Configuration
# -----------------------------------------------------------------------------
application_logger = logging.getLogger('application')


class DatabaseConfiguredSMSBackend:
    """
    Dynamic SMS Backend Loader / Strategy Executor.
    
    ---------------------------------------------------------------------------
    Architectural Purpose:
    ---------------------------------------------------------------------------
    This class serves as the Bridge between the abstract `SMSManager` (High Level)
    and the concrete Provider Implementations (Low Level, e.g., Twilio, Termii).
    
    It implements a dynamic loading strategy:
    1.  Queries the Database (`SMSBackendConfig`) to find the Administrator's 
        preferred Provider Class Path string.
    2.  Uses Python's `import_string` to dynamically import that class from code.
    3.  Instantiates the class.
    4.  Delegates the actual message sending to that instance.
    
    Features:
    - **Fail-Safe Fallback**: If, for any reason, the configured backend fails 
      to load (syntax error, missing file, database down), this class 
      automatically falls back to the Default Provider (`TwilioSMSProvider`) to 
      ensure the system remains operational.
    - **Unified Interface**: It exposes a `.send_messages()` method that normalizes 
      interaction, so the Manager doesn't need to know the specifics of the 
      underlying provider.
    """

    def __init__(self, *args, **kwargs):
        """
        Initializes the SMS backend by resolving and loading the active provider.

        The constructor performs the heavy lifting of:
        1. DB Lookup.
        2. Dynamic Import.
        3. Instantiation.
        4. Error Handling & Fallback.

        Args:
            *args: Variable positional arguments (passed down if needed).
            **kwargs: Variable keyword arguments (passed down if needed).
        """
        
        try:
            # -----------------------------------------------------------------
            # 1. Database Lookup
            # -----------------------------------------------------------------
            # We use apps.get_model to avoid circular imports.
            SMSBackendConfig = apps.get_model('admin_backend', 'SMSBackendConfig')
            config = SMSBackendConfig.objects.first()

            # -----------------------------------------------------------------
            # 2. Path Resolution
            # -----------------------------------------------------------------
            if config:
                if config.sms_backend:
                    self.provider_path = config.sms_backend
                    application_logger.info(f"Using SMS provider from database config: {self.provider_path}")
                else:
                    # Config exists but field empty (rare edge case)
                    self.provider_path = 'apps.common.providers.SMS.twilio.TwilioSMSProvider'
                    application_logger.warning("SMSBackendConfig found but 'sms_backend' field is empty. Defaulting to Twilio.")
            else:
                # No config in DB yet
                self.provider_path = 'apps.common.providers.SMS.twilio.TwilioSMSProvider'
                application_logger.warning("No SMSBackendConfig found in database. Defaults to using Twilio.")

            # -----------------------------------------------------------------
            # 3. Dynamic Import & Instantiation
            # -----------------------------------------------------------------
            # This is where the magic happens. 'import_string' turns the string
            # 'apps.common...TwilioSMSProvider' into the actual Class object.
            provider_class = import_string(self.provider_path)
            
            # Instantiate the provider. The provider's __init__ will usually 
            # load its own credentials from Settings.
            self.sms_provider = provider_class()
            
            application_logger.info(f"✅ SMS Backend successfully initialized with active provider: {provider_class.__name__}")

        except ImportError as ie:
            application_logger.error(f"❌ Import Error initializing SMS backend: {ie}. Path was: {getattr(self, 'provider_path', 'unknown')}", exc_info=True)
            self._activate_fallback_backend()
            
        except Exception as e:
            application_logger.error(f"❌ Critical Error initializing SMS backend: {e}", exc_info=True)
            self._activate_fallback_backend()

    def _activate_fallback_backend(self):
        """
        Helper method to activate the fallback provider (Twilio) 
        when the primary configuration fails.
        """
        try:
            from apps.common.providers.SMS.twilio import TwilioSMSProvider
            self.sms_provider = TwilioSMSProvider()
            application_logger.info("🔄 SYSTEM FALLBACK: SMS Backend initialized with Default Twilio provider due to previous error.")
        except Exception as fallback_error:
            # If even the fallback fails, we are in trouble.
            application_logger.critical(f"❌❌ CATASTROPHIC FAILURE: Fallback SMS Provider failed to initialize: {fallback_error}", exc_info=True)
            raise

    def send_messages(self, sms_messages):
        """
        Sends a batch of SMS messages using the configured provider.

        This method provides a generic interface for bulk sending. 
        It iterates through the provided message list and delegates each one 
        to the underlying provider's `.send()` method.

        Args:
            sms_messages (list): A list of dictionaries or objects.
                                 Each item MUST have 'to' and 'body' attributes/keys.

        Returns:
            list: A list of results (IDs or Statuses) for each message processed.

        Raises:
            Exception: Propagates unhandled exceptions from the provider 
                       (after logging them).
        """
        results = []
        try:
            for message in sms_messages:
                # Extract Data safely
                to = message.get('to')
                body = message.get('body')
                
                # Validation
                if not to or not body:
                    application_logger.warning(f"⏩ Skipping invalid SMS message payload: {message}")
                    results.append({'status': 'failed', 'reason': 'invalid_payload'})
                    continue

                # Delegate to concrete provider
                try:
                    # The provider's send method returns the Message SID/ID
                    result = self.sms_provider.send(to, body)
                    results.append(result)
                    application_logger.info(f"SMS explicitly sent to {to} via {self.sms_provider.__class__.__name__}")
                    
                except Exception as inner_e:
                    # We catch per-message errors so one bad number doesn't fail the whole batch
                    error_msg = f"Error sending to {to}: {str(inner_e)}"
                    application_logger.error(error_msg)
                    results.append({'status': 'failed', 'reason': str(inner_e)})

            return results

        except Exception as e:
            # Top level error (e.g., iterating the list failed)
            application_logger.error(f"❌ Error in SMS batch processing loop: {e}", exc_info=True)
            raise
