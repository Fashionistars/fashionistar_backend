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

    # Resolve conflicts with legacy User model
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name=_('groups'),
        blank=True,
        help_text=_(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        related_name="unified_user_set",
        related_query_name="unified_user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name=_('user permissions'),
        blank=True,
        help_text=_('Specific permissions for this user.'),
        related_name="unified_user_set",
        related_query_name="unified_user",
    )
    
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

    # Identification — username removed in favor of email/phone
    username = None
    email = models.EmailField(
        _('email address'),
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Primary unique identifier for email-based auth.",
    )
    phone = PhoneNumberField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Primary unique identifier for phone-based auth.",
    )

    # Profile Data (Merged from legacy Profile)
    avatar = models.ImageField(
        upload_to="avatars/%Y/%m/",
        default="default/default-user.jpg",
        help_text="User's profile picture.",
    )
    bio = models.TextField(
        blank=True,
        help_text="User's biography.",
    )

    # Location (Essential for Logistics)
    country = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="User's country.",
    )
    state = models.CharField(
        max_length=100,
        blank=True,
        help_text="User's state or province.",
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        help_text="User's city.",
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        help_text="User's street address.",
    )

    # System Fields
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_CLIENT,
        db_index=True,
        help_text="RBAC Role. Cannot be changed after creation.",
    )
    auth_provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_EMAIL,
        help_text="Authentication provider used at signup.",
    )
    is_verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if email/phone OTP is verified.",
    )
    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if user account is active.",
    )

    # Legacy Support
    pid = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        help_text="Legacy unique identifier for backward compatibility.",
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone']

    objects = CustomUserManager()

    class Meta:
        verbose_name = "Unified User"
        verbose_name_plural = "Unified Users"
        ordering = ["-date_joined"]

        indexes = [
            # Single-field indexes for fast lookups
            models.Index(
                fields=['email'],
                name='uu_email_idx',
            ),
            models.Index(
                fields=['phone'],
                name='uu_phone_idx',
            ),
            models.Index(
                fields=['role'],
                name='uu_role_idx',
            ),
            models.Index(
                fields=['is_verified'],
                name='uu_is_verified_idx',
            ),
            models.Index(
                fields=['is_active'],
                name='uu_is_active_idx',
            ),
            models.Index(
                fields=['auth_provider'],
                name='uu_auth_provider_idx',
            ),
            models.Index(
                fields=['country'],
                name='uu_country_idx',
            ),
            # Composite indexes for common query patterns
            models.Index(
                fields=['email', 'role'],
                name='uu_email_role_idx',
            ),
            models.Index(
                fields=['phone', 'role'],
                name='uu_phone_role_idx',
            ),
            models.Index(
                fields=['auth_provider', 'is_verified'],
                name='uu_provider_verified_idx',
            ),
            models.Index(
                fields=['role', 'is_active'],
                name='uu_role_active_idx',
            ),
        ]

    def __str__(self):
        return (
            str(self.email) if self.email
            else str(self.phone) if self.phone
            else "No Email or Phone"
        )

    @property
    def identifying_info(self):
        """
        Return the primary identifier, prioritizing email.
        Used consistently in logging and admin displays.
        """
        return (
            str(self.email) if self.email
            else str(self.phone) if self.phone
            else "No Email or Phone"
        )

    def clean(self):
        """
        STRICT VALIDATION: Enforces business rules at the
        Database Model level.

        - New users: mutual-exclusivity, uniqueness, role check.
        - Existing users: immutability guards on identity fields.
        """
        super().clean()

        if self._state.adding:
            # ── NEW USER VALIDATION ──────────────────────────
            # Note: we use ``self._state.adding`` instead of
            # ``not self.pk`` because UUID primary keys are
            # auto-generated at __init__ time, making self.pk
            # always truthy.

            # 1. Mutually Exclusive Identifiers
            #    (Email OR Phone, unless Google)
            if self.auth_provider != self.PROVIDER_GOOGLE:
                if self.email and self.phone:
                    raise ValidationError(
                        _('Please provide either an Email '
                          'Address or a Phone Number, '
                          'Not Both.')
                    )
                if not self.email and not self.phone:
                    raise ValidationError(
                        _('Either Email or Phone is required.')
                    )

            # 2. Auth Provider ↔ Identifier Cross-Validation
            #    (CRITICAL SECURITY FIX)
            if self.auth_provider == 'email' and not self.email:
                raise ValidationError({
                    'auth_provider': _(
                        'Auth provider "email" requires an email '
                        'address to be provided.'
                    ),
                })
            if self.auth_provider == 'phone' and not self.phone:
                raise ValidationError({
                    'auth_provider': _(
                        'Auth provider "phone" requires a phone '
                        'number to be provided.'
                    ),
                })
            if (
                self.auth_provider == 'email'
                and self.email
                and self.phone
            ):
                raise ValidationError(
                    _('Email auth provider should not have '
                      'a phone number. Use email only.')
                )
            if (
                self.auth_provider == 'phone'
                and self.phone
                and self.email
            ):
                raise ValidationError(
                    _('Phone auth provider should not have '
                      'an email address. Use phone only.')
                )

            # 2. Google Auth Requirement
            if (
                self.auth_provider == self.PROVIDER_GOOGLE
                and not self.email
            ):
                raise ValidationError(
                    _('Google authentication requires '
                      'an email address.')
                )

            # 3. Check for duplicate Email
            if (
                self.email
                and UnifiedUser.objects.filter(
                    email=self.email
                ).exists()
            ):
                raise ValidationError(
                    {'email': _('This email is already in use.')}
                )

            # 4. Check for duplicate Phone
            if (
                self.phone
                and UnifiedUser.objects.filter(
                    phone=self.phone
                ).exists()
            ):
                raise ValidationError(
                    {'phone': _(
                        'This phone number is already in use.'
                    )}
                )

            # 5. Role Validation against ROLE_CHOICES
            valid_roles = dict(self.ROLE_CHOICES).keys()
            if self.role not in valid_roles:
                raise ValidationError(
                    {'role': _(
                        'Invalid role value. Must be one of: '
                        + ', '.join(valid_roles)
                    )}
                )

        else:
            # ── EXISTING USER — IMMUTABILITY GUARDS ─────────
            # ``self._state.adding`` is False for DB-loaded
            # instances, safe to query for the existing row.
            existing = UnifiedUser.objects.all_with_deleted().get(
                pk=self.pk,
            )

            # Prevent email modification
            if (
                existing.email is not None
                and self.email != existing.email
            ):
                raise ValidationError(
                    {'email': _(
                        'Email cannot be changed after '
                        'user creation.'
                    )}
                )

            # Prevent phone modification
            if (
                existing.phone is not None
                and self.phone != existing.phone
            ):
                raise ValidationError(
                    {'phone': _(
                        'Phone cannot be changed after '
                        'user creation.'
                    )}
                )

            # Prevent role modification
            if self.role != existing.role:
                raise ValidationError(
                    {'role': _(
                        'Role cannot be changed after '
                        'user creation.'
                    )}
                )

            # Prevent auth_provider modification
            if self.auth_provider != existing.auth_provider:
                raise ValidationError(
                    {'auth_provider': _(
                        'Auth provider cannot be changed '
                        'after user creation.'
                    )}
                )

            # Log the update action
            logger.info(
                "Details updated for user: %s",
                existing.identifying_info,
            )

        return None

    def save(self, *args, **kwargs):
        """
        Save method to enforce validation and NULL normalization.
        Ensures email and phone are stored as NULL instead of
        empty strings to preserve UNIQUE constraint integrity.
        """
        self.full_clean()

        # Normalize empty strings → NULL
        if not self.email:
            self.email = None
        if not self.phone:
            self.phone = None

        super().save(*args, **kwargs)
        logger.info(
            "Saved UnifiedUser %s [%s]",
            self.pk,
            self.auth_provider,
        )

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
