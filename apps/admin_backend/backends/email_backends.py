# admin_backend/backends/email_backends.py
from django.core.mail.backends.base import BaseEmailBackend
from django.apps import apps
from django.conf import settings
import logging

application_logger = logging.getLogger('application')

class DatabaseConfiguredEmailBackend(BaseEmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            EmailBackendConfig = apps.get_model('admin_backend', 'EmailBackendConfig')
            config = EmailBackendConfig.objects.first()
            if config:
                self.email_backend_path = config.email_backend
                application_logger.info(f"Using email backend from database config: {self.email_backend_path}")
            else:
                self.email_backend_path = 'django.core.mail.backends.smtp.EmailBackend'  # Default
                application_logger.warning("No EmailBackendConfig found, using default SMTP backend.")

            # Dynamically import and instantiate the email backend class
            module_path, class_name = self.email_backend_path.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            backend_class = getattr(module, class_name)

            self.email_backend = backend_class(*args, **kwargs)

        except Exception as e:
            application_logger.error(f"Error initializing email backend: {e}", exc_info=True)
            self.email_backend_path = 'django.core.mail.backends.smtp.EmailBackend' # Default to SMTP on error.
            from django.core.mail.backends.smtp import EmailBackend
            self.email_backend = EmailBackend(*args, **kwargs)  # Fallback to SMTP.

    def send_messages(self, email_messages):
        return self.email_backend.send_messages(email_messages)
