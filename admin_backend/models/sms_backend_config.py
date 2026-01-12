from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

class SMSBackendConfig(models.Model):
    SMS_BACKEND_CHOICES = [
        ('apps.common.providers.SMS.twilio.TwilioSMSProvider', 'Twilio'),
        ('apps.common.providers.SMS.termii.TermiiSMSProvider', 'Termii'),
        ('apps.common.providers.SMS.bulksmsNG.BulksmsNGSMSProvider', 'BulkSMS Nigeria'),
    ]
    
    sms_backend = models.CharField(
        max_length=250,
        choices=SMS_BACKEND_CHOICES,
        default='apps.common.providers.SMS.twilio.TwilioSMSProvider',
        verbose_name='Select SMS Backend',
        help_text=_("Choose the SMS provider you wish to use. Ensure usage credentials (API Keys) are set in your environment variables."),
        db_index=True
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return dict(self.SMS_BACKEND_CHOICES).get(self.sms_backend, "SMS Backend Configuration")

    class Meta:
        verbose_name = "SMS Backend Configuration"
        verbose_name_plural = "SMS Backend Configuration"
        indexes = [
            models.Index(fields=['sms_backend'], name='sms_backend_idx'),
        ]

    def clean(self):
        super().clean()
        if self.pk is None and SMSBackendConfig.objects.exists():
            raise ValidationError(_("You cannot create a new instance once the first one is created. Edit the existing one instead."))

    def delete(self, *args, **kwargs):
        raise ValidationError(_("You cannot DELETE this configuration. You can only EDIT needs."))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
