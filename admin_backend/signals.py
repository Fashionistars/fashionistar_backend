# admin_backend/signals.py
from django.conf import settings
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.apps import apps
import logging

# Initialize application logger
application_logger = logging.getLogger('application')


@receiver(post_migrate)
def create_backend_configs(sender, **kwargs):
    """
    Signal receiver that runs after migrations are complete for the admin_backend app.
    
    This function ensures that the critical backend configuration models
    (EmailBackendConfig and SMSBackendConfig) have at least one singleton instance
    created in the database. This allows the system to function immediately
    without manual admin intervention.
    """
    if sender.name == 'admin_backend':
        try:
            # --- Email Backend Configuration ---
            EmailBackendConfig = apps.get_model('admin_backend', 'EmailBackendConfig')  # Get model dynamically to avoid circular imports

            if not EmailBackendConfig.objects.exists():
                EmailBackendConfig.objects.create()
                application_logger.info("EmailBackendConfig singleton instance automatically created via post_migrate signal.")
            else:
                application_logger.info("EmailBackendConfig instance already exists. Skipping creation.")

            # --- SMS Backend Configuration ---
            SMSBackendConfig = apps.get_model('admin_backend', 'SMSBackendConfig') # Get model dynamically

            if not SMSBackendConfig.objects.exists():
                SMSBackendConfig.objects.create()
                application_logger.info("SMSBackendConfig singleton instance automatically created via post_migrate signal.")
            else:
                application_logger.info("SMSBackendConfig instance already exists. Skipping creation.")

        except Exception as e:
            application_logger.error(f"Critical Error creating backend config instances during post_migrate: {e}", exc_info=True)