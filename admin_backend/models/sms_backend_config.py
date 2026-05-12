# admin_backend/models/sms_backend_config.py

from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

class SMSBackendConfig(models.Model):
    """
    Configuration for SMS backend providers.
    
    ---------------------------------------------------------------------------
    Architectural Purpose:
    ---------------------------------------------------------------------------
    This model serves as the Central Configuration Point for the entire Application's
    SMS sending capabilities. It allows the Super Admin to dynamically switch 
    between different SMS Providers (Twilio, Termii, BulkSMSNG) without 
    changing a single line of code or redeploying the server.
    
    It works by storing the Python import path to the Provider Class that should 
    be instantiated by the `SMSManager`.
    
    Design Pattern:
    - **Strategy Pattern (Dynamic Selection)**: The application asks for "An SMS Provider",
      and this model tells it "Which One" to use.
    - **Singleton Pattern (enforced via clean/save)**: Only ONE Active configuration
      should exist at any time to prevent system ambiguity.
      
    Security Note:
    - This model ONLY selects the Provider Class.
    - Actual API Secrets and Keys are strictly read from Environment Variables
      (`settings.py`) to prevent sensitive data exposure in the database.
    """
    
    # -------------------------------------------------------------------------
    # Choices Configuration
    # -------------------------------------------------------------------------
    # Define available provider paths. These must map to actual python classes
    # existing in the codebase.
    SMS_BACKEND_CHOICES = [
        ('apps.common.providers.SMS.twilio.TwilioSMSProvider', 'Twilio (Global/Robust)'),
        ('apps.common.providers.SMS.termii.TermiiSMSProvider', 'Termii (Nigeria Focused)'),
        ('apps.common.providers.SMS.bulksmsNG.BulksmsNGSMSProvider', 'BulkSMS Nigeria (Cost Effective)'),
    ]
    
    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------
    
    sms_backend = models.CharField(
        max_length=250,
        choices=SMS_BACKEND_CHOICES,
        default='apps.common.providers.SMS.twilio.TwilioSMSProvider',
        verbose_name='Select SMS Backend Provider',
        help_text=_(
            "Choose the active SMS provider class for the system. "
            "NOTE: Ensure the corresponding API Credentials (Keys/Secrets) are "
            "correctly set in your Server Environment Variables before switching."
        ),
        db_index=True  # Indexed for faster lookup during provider initialization
    )

    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="The timestamp when this configuration was first created."
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="The timestamp when this configuration was last modified."
    )

    # -------------------------------------------------------------------------
    # Meta / String Representation
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "SMS Backend Configuration"
        verbose_name_plural = "SMS Backend Configuration"
        # Database index to ensure quick retrival by the backend loader
        indexes = [
            models.Index(fields=['sms_backend'], name='sms_backend_idx'),
        ]

    def __str__(self):
        """String representation showing the friendly name of the selected backend."""
        return dict(self.SMS_BACKEND_CHOICES).get(self.sms_backend, "SMS Backend Configuration")

    # -------------------------------------------------------------------------
    # Validation & Logic Enforcement
    # -------------------------------------------------------------------------

    def clean(self):
        """
        Enforce Singleton Constraint during Model Validation.
        
        This ensures that a user cannot inadvertently create a second configuration
        instance via the Admin Panel, which would lead to ambiguous system behavior.
        If an instance already exists, we block the creation of a new one.
        """
        super().clean()
        # If this is a new instance (pk is None) and one already exists...
        if self.pk is None and SMSBackendConfig.objects.exists():
            raise ValidationError(
                _("Singleton Error: You cannot create a new instance once the first one is created. "
                  "Please Go Back and EDIT the existing configuration instead.")
            )

    def delete(self, *args, **kwargs):
        """
        Prevent Deletion of the Configuration.
        
        The system requires at least one configuration to function. Therefore,
        deletion is strictly prohibited. Users must EDIT the existing instance
        to change providers.
        """
        raise ValidationError(
            _("Critical Error: You cannot DELETE this SMS Backend Configuration!!!. "
              "This configuration is required for the sending subsystem to function. "
              "Please EDIT it to your preferred provider instead.")
        )

    def save(self, *args, **kwargs):
        """
        Override Save to ensure validation is run.
        """
        self.full_clean()  # Force the clean() method validation before saving
        super().save(*args, **kwargs)
