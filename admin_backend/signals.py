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