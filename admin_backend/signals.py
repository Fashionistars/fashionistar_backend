# admin_backend/signals.py
from django.conf import settings
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.apps import apps
import logging

application_logger = logging.getLogger('application')


@receiver(post_migrate)
def create_email_backend_config(sender, **kwargs):
    """
    Signal receiver that runs after migrations are complete for the admin_backend app.
    Creates the EmailBackendConfig instance if it doesn't exist.
    """
    if sender.name == 'admin_backend':
        try:
            EmailBackendConfig = apps.get_model('admin_backend', 'EmailBackendConfig')  # Get model dynamically

            if not EmailBackendConfig.objects.exists():
                EmailBackendConfig.objects.create()
                application_logger.info("EmailBackendConfig instance created via post_migrate signal.")
            else:
                application_logger.info("EmailBackendConfig instance already exists.")

        except Exception as e:
            application_logger.error(f"Error creating/accessing EmailBackendConfig instance from post_migrate: {e}", exc_info=True)


@receiver(post_migrate)
def create_sms_backend_config(sender, **kwargs):
    """
    Signal receiver that runs after migrations are complete for the admin_backend app.
    Creates a default SMSBackendConfig instance if none exist.
    """
    if sender.name == 'admin_backend':
        try:
            SMSBackendConfig = apps.get_model('admin_backend', 'SMSBackendConfig')  # Get model dynamically

            if not SMSBackendConfig.objects.exists():
                # The model now defaults to Twilio and uses env vars for credentials.
                # We just need to create the entry with defaults.
                SMSBackendConfig.objects.create() 
                application_logger.info("Default SMSBackendConfig instance created via post_migrate signal.")
            else:
                application_logger.info("SMSBackendConfig instance already exists.")

        except Exception as e:
            application_logger.error(f"Error creating/accessing SMSBackendConfig instance from post_migrate: {e}", exc_info=True)