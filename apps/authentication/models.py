from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from apps.common.models import TimeStampedModel, SoftDeleteModel, HardDeleteMixin
from phonenumber_field.modelfields import PhoneNumberField
from auditlog.registry import auditlog
from apps.authentication.managers import CustomUserManager
import logging

logger = logging.getLogger('application')

class UnifiedUser(AbstractUser, TimeStampedModel, SoftDeleteModel, HardDeleteMixin):
    """
    The Central Identity Entity.
    
    Merged Fields from legacy Profile:
    - bio, phone, avatar (was image), country, city, state, address.
    
    New Architecture Fields:
    - auth_provider: Tracks if user signed up via Email, Phone, or Google.
    - role: RBAC (Role Based Access Control).
    """
    
    # Auth Providers
    PROVIDER_EMAIL = "email"
    PROVIDER_PHONE = "phone"
    PROVIDER_GOOGLE = "google"
    
    PROVIDER_CHOICES = [
        (PROVIDER_EMAIL, "Email"),
        (PROVIDER_PHONE, "Phone"),
        (PROVIDER_GOOGLE, "Google"),
    ]

    # Roles
    ROLE_VENDOR = "vendor"
    ROLE_CLIENT = "client"
    ROLE_STAFF = "staff"
    ROLE_ADMIN = "admin"
    ROLE_EDITOR = "editor"
    ROLE_SUPPORT = "support"
    ROLE_ASSISTANT = "assistant"
    
    ROLE_CHOICES = [
        (ROLE_VENDOR, "Vendor"),
        (ROLE_CLIENT, "Client"),
        (ROLE_STAFF, "Staff"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_EDITOR, "Editor"),
        (ROLE_SUPPORT, "Support"),
        (ROLE_ASSISTANT, "Assistant"),
    ]

    # Identification
    username = None  # Removed to use email/phone
    email = models.EmailField(
        _('email address'), 
        unique=True, 
        null=True, 
        blank=True,
        db_index=True, 
        help_text="Primary unique identifier for email-based auth."
    )
    phone = PhoneNumberField(
        unique=True, 
        null=True, 
        blank=True,
        db_index=True, 
        help_text="Primary unique identifier for phone-based auth."
    )
    
    # Profile Data (Merged)
    avatar = models.ImageField(
        upload_to="avatars/%Y/%m/", 
        default="default/default-user.jpg", 
        help_text="User's profile picture."
    )
    bio = models.TextField(blank=True, help_text="User's biography.")
    
    # Location (Essential for Logistics)
    country = models.CharField(max_length=100, blank=True, db_index=True, help_text="User's country.")
    state = models.CharField(max_length=100, blank=True, help_text="User's state.")
    city = models.CharField(max_length=100, blank=True, help_text="User's city.")
    address = models.CharField(max_length=255, blank=True, help_text="User's address.")
    
    # System Fields
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default=ROLE_CLIENT, 
        db_index=True, 
        help_text="RBAC Role. Cannot be changed after creation easily."
    )
    auth_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_EMAIL, help_text="Authentication provider used.")
    is_verified = models.BooleanField(default=False, db_index=True, help_text="True if email/phone OTP is verified.")
    
    # Legacy Support
    pid = models.CharField(max_length=50, unique=True, null=True, help_text="Unique identifier.")

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone']

    objects = CustomUserManager()

    class Meta:
        verbose_name = "Unified User"
        verbose_name_plural = "Unified Users"
        indexes = [
            models.Index(fields=['email', 'role']),
            models.Index(fields=['phone', 'role']),
            models.Index(fields=['auth_provider', 'is_verified']),
        ]

    def __str__(self):
        return self.email if self.email else str(self.phone)

    def clean(self):
        """
        STRICT VALIDATION: Enforces business rules at the Database Model level.
        """
        super().clean()
        
        # 1. Mutually Exclusive Identifiers (Email OR Phone, unless Google)
        if self.auth_provider != self.PROVIDER_GOOGLE:
            if self.email and self.phone:
                raise ValidationError(_('Please provide either an Email Address or a Phone Number, Not Both.'))
            if not self.email and not self.phone:
                raise ValidationError(_('Either Email or Phone is required.'))

        # 2. Google Auth Requirement
        if self.auth_provider == self.PROVIDER_GOOGLE and not self.email:
            raise ValidationError(_('Google authentication requires an email address.'))
            
        # 3. Check for duplicate Email
        if self.email and UnifiedUser.objects.exclude(pk=self.pk).filter(email=self.email).exists():
             raise ValidationError({'email': _('This email is already in use.')})

        # 4. Check for duplicate Phone
        if self.phone and UnifiedUser.objects.exclude(pk=self.pk).filter(phone=self.phone).exists():
             raise ValidationError({'phone': _('This phone number is already in use.')})

    def save(self, *args, **kwargs):
        """
        Override save to inject robust logging and validation.
        """
        try:
            self.full_clean()  # Validate before save
            # Normalizing empty strings to None to enforce UNIQUE constraints
            if self.email == "": self.email = None
            if self.phone == "": self.phone = None
            
            super().save(*args, **kwargs)
            logger.info(f"💾 Saved UnifiedUser {self.pk} [{self.auth_provider}]")
        except Exception as e:
            logger.error(f"❌ Error saving UnifiedUser: {str(e)}")
            raise

    def is_owner(self, user):
        """
        Ownership check for HardDeleteMixin.
        """
        return self.pk == user.pk

class BiometricCredential(TimeStampedModel):
    """
    Stores FIDO2/WebAuthn credentials for Passwordless/Biometric Auth.
    """
    user = models.ForeignKey(
        UnifiedUser, 
        on_delete=models.CASCADE, 
        related_name='biometric_credentials',
        help_text="The user this credential belongs to."
    )
    credential_id = models.BinaryField(unique=True, help_text="The Credential ID generated by the authenticator.")
    public_key = models.BinaryField(help_text="The Public Key for signature verification.")
    sign_count = models.IntegerField(default=0, help_text="Counter to prevent replay attacks.")
    device_name = models.CharField(max_length=255, blank=True, null=True, help_text="User-friendly name (e.g., 'MacBook TouchID').")

    class Meta:
        verbose_name = "Biometric Credential"
        verbose_name_plural = "Biometric Credentials"

    def __str__(self):
        return f"{self.user.email} - {self.device_name or 'Key'}"
