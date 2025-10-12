# admin_backend/models/email_backend_config.py
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _  # For internationalization

class EmailBackendConfig(models.Model):
    EMAIL_BACKEND_CHOICES = [
        ('django.core.mail.backends.smtp.EmailBackend', 'SMTP (Gmail)'),
        ('django.core.mail.backends.console.EmailBackend', 'Console'),
        ('anymail.backends.mailgun.EmailBackend', 'Mailgun'),
        ('zoho_zeptomail.backend.zeptomail_backend.ZohoZeptoMailEmailBackend', 'Zoho ZeptoMail'),
        # Add SendGrid when/if you need it later:
        ('anymail.backends.sendgrid.EmailBackend', 'SendGrid'),
    ]
    email_backend = models.CharField(
        max_length=250,  # Increased max length
        choices=EMAIL_BACKEND_CHOICES,
        default='django.core.mail.backends.smtp.EmailBackend',  # Gmail is often a good default
        verbose_name='Select Email Backend',
        help_text=_("Choose the email backend you wish to use for sending emails.  Consider factors like reliability, cost, and integration with your existing infrastructure.  SMTP (Gmail) is suitable for development or low-volume sending. For production environments, consider Mailgun, SendGrid, or Zoho ZeptoMail."),
        db_index=True  # Add a database index
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        # Get the display name of the chosen email backend
        return dict(self.EMAIL_BACKEND_CHOICES).get(self.email_backend, "Email Backend Configuration")

    class Meta:
        verbose_name = "Email Backend Configuration"
        verbose_name_plural = "Email Backend Configuration"
        indexes = [
            models.Index(fields=['email_backend'], name='email_backend_idx'),
        ]

    def clean(self):
        super().clean()
        if self.pk is None:  # It's a new instance
            if EmailBackendConfig.objects.exists():
                raise ValidationError(_("You cannot create a new instance once the first one is created. Instead, you can edit the already existing one to your preferred SMTP provider."))

    def delete(self, *args, **kwargs):
        raise ValidationError(_("You cannot DELETE this Email Backend Configuration instance!!!.  This configuration is required for sending emails.!!!   You can Only EDIT to your preferred SMTP provider."))

    def save(self, *args, **kwargs):
        self.full_clean()  # Ensure clean() is called before saving.
        super().save(*args, **kwargs)