# admin_backend/models/email_backend_config.py
"""Admin-managed email backend selection for Fashionistar."""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.providers.SMTP import EMAIL_BACKEND_CHOICES, get_email_backend_label

class EmailBackendConfig(models.Model):
    """Stores the single active email delivery backend for the platform."""

    EMAIL_BACKEND_CHOICES = EMAIL_BACKEND_CHOICES
    email_backend = models.CharField(
        max_length=250,
        choices=EMAIL_BACKEND_CHOICES,
        default="django.core.mail.backends.smtp.EmailBackend",
        verbose_name="Select Email Backend",
        help_text=_(
            "Choose the transactional email backend used by the platform. "
            "SMTP (Gmail) is acceptable for development or low-volume flows. "
            "Production environments should use Mailgun, SendGrid, Zoho "
            "ZeptoMail, or Brevo."
        ),
        db_index=True,
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        """Return the human-friendly label for the configured backend."""

        return get_email_backend_label(self.email_backend)

    class Meta:
        verbose_name = "Email Backend Configuration"
        verbose_name_plural = "Email Backend Configuration"
        indexes = [models.Index(fields=["email_backend"], name="email_backend_idx")]

    def clean(self):
        """Allow only one persistent backend configuration row."""

        super().clean()
        if self.pk is None:
            if EmailBackendConfig.objects.exists():
                raise ValidationError(
                    _(
                        "You cannot create a new instance once the first one is "
                        "created. Edit the existing configuration instead."
                    )
                )

    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton email backend configuration."""

        raise ValidationError(
            _(
                "You cannot delete the Email Backend Configuration. "
                "Edit it to switch providers instead."
            )
        )

    def save(self, *args, **kwargs):
        """Validate the singleton rule before persisting the record."""

        self.full_clean()
        super().save(*args, **kwargs)
