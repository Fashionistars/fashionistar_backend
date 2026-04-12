# apps/authentication/models/unified_user.py
"""
UnifiedUser Model — Central Identity Entity
============================================

The primary user model for the Fashionistar platform.
Replaces Django's default User model with a unified, multi-provider auth system.

Key Features:
  - Email OR Phone as primary identifier (mutually exclusive by auth_provider)
  - Google OAuth support (email + phone allowed together)
  - Cloudinary avatar via 2-phase direct-upload webhook pattern
  - Human-readable ``member_id`` (FASTAR000001) via atomic counter
  - Role-Based Access Control (RBAC) with 7 roles
  - SoftDelete support via SoftDeleteModel mixin
  - Audit logging via django-auditlog

Import:
    from apps.authentication.models import UnifiedUser, MemberIDCounter
"""

import logging

from apps.authentication.managers import CustomUserManager
from apps.common.models import HardDeleteMixin, SoftDeleteModel, TimeStampedModel
from auditlog.registry import auditlog
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

logger = logging.getLogger(__name__)


# ================================================================
# MEMBER ID — Race-safe human-readable user identifier
# Format: FASTAR0001 ... FASTAR9999 (10 chars, all caps)
# ================================================================

MEMBER_ID_PREFIX = "FASTAR"
MEMBER_ID_DIGITS = 6  # 000001 – 999999


class MemberIDCounter(models.Model):
    """
    Single-row atomic counter for ``member_id`` generation.

    Uses ``select_for_update()`` inside a transaction to guarantee
    no two concurrent user-creation requests receive the same
    sequence number. The table always has exactly one row (id=1).

    Never instantiate or delete this model manually.
    """

    counter = models.PositiveIntegerField(
        default=0,
        help_text="Current highest sequence number issued.",
    )

    class Meta:
        verbose_name = "Member ID Counter"
        db_table = "authentication_member_id_counter"

    @classmethod
    def next_value(cls):
        """
        Atomically increment and return the next sequence number.

        Returns:
            int: The next available counter value (1-indexed).

        Raises:
            OverflowError: If the counter would exceed the maximum
                representable value for the digit width (9999).
        """
        max_value = 10 ** MEMBER_ID_DIGITS - 1  # 999999

        with transaction.atomic():
            obj, _ = cls.objects.select_for_update().get_or_create(
                id=1,
                defaults={'counter': 0},
            )
            if obj.counter >= max_value:
                raise OverflowError(
                    f"MemberIDCounter has reached the maximum value "
                    f"({max_value}). Extend MEMBER_ID_DIGITS to continue."
                )
            obj.counter = F('counter') + 1
            obj.save(update_fields=['counter'])
            obj.refresh_from_db(fields=['counter'])
            return obj.counter


def generate_member_id():
    """
    Generate a unique, human-readable, brand-aligned member ID.

    Format:  ``FASTAR`` + zero-padded 6-digit counter
    Example: ``FASTAR000001``, ``FASTAR000062``, ``FASTAR001337``

    The counter is sourced from ``MemberIDCounter.next_value()``
    which uses row-level locking (``SELECT FOR UPDATE``) to
    guarantee uniqueness under concurrent writes.

    Returns:
        str: A 12-character uppercase string.
    """
    seq = MemberIDCounter.next_value()
    return f"{MEMBER_ID_PREFIX}{seq:0{MEMBER_ID_DIGITS}d}"


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

    # Redefine name fields to allow NULL (User Request for consistency)
    first_name = models.CharField(
        _("first name"), max_length=150, blank=True, null=True
    )
    last_name = models.CharField(
        _("last name"), max_length=150, blank=True, null=True
    )

    # --- ARCHITECTURE NOTE ---
    # avatar is now a plain URLField that stores the Cloudinary HTTPS secure_url.
    # Uploads go through the two-phase direct-upload pattern:
    #   1. Frontend calls POST /api/v1/upload/presign/ → gets a signed upload token
    #   2. Frontend POSTs file DIRECTLY to Cloudinary (bypasses Django server)
    #   3. Cloudinary calls our webhook → Celery task saves the secure_url here
    # This eliminates all synchronous cloudinary.uploader.upload() inside save().
    avatar = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text=(
            "Cloudinary HTTPS secure_url for user avatar. "
            "Set via the /api/v1/upload/presign/ → direct upload → webhook flow. "
            "Paste a Cloudinary URL directly in the admin if needed."
        ),
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

    # ── Human-Readable Public Identifier ─────────────────────
    member_id = models.CharField(
        max_length=12,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        db_index=True,
        help_text=(
            "Unique human-readable brand ID (e.g. FASTAR000062). "
            "Auto-generated on user creation. Cannot be changed."
        ),
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone']

    objects = CustomUserManager()

    class Meta:
        verbose_name = "Unified User"
        verbose_name_plural = "Unified Users"
        ordering = ["-date_joined"]

        indexes = [
            models.Index(fields=['email'],          name='uu_email_idx'),
            models.Index(fields=['phone'],          name='uu_phone_idx'),
            models.Index(fields=['role'],           name='uu_role_idx'),
            models.Index(fields=['is_verified'],    name='uu_is_verified_idx'),
            models.Index(fields=['is_active'],      name='uu_is_active_idx'),
            models.Index(fields=['auth_provider'],  name='uu_auth_provider_idx'),
            models.Index(fields=['country'],        name='uu_country_idx'),
            models.Index(fields=['email', 'role'],  name='uu_email_role_idx'),
            models.Index(fields=['phone', 'role'],  name='uu_phone_role_idx'),
            models.Index(fields=['auth_provider', 'is_verified'], name='uu_provider_verified_idx'),
            models.Index(fields=['role', 'is_active'],            name='uu_role_active_idx'),
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
        STRICT VALIDATION: Enforces business rules at the Database Model level.
        """
        super().clean()

        # Re-apply NULL normalisation (undoes AbstractUser.clean() side-effect)
        if not self.email:
            self.email = None
        if not self.phone:
            self.phone = None

        if self._state.adding:
            # NEW USER VALIDATION
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
            if (self.auth_provider == 'email' and self.email and self.phone):
                raise ValidationError(
                    _('Email auth provider should not have '
                      'a phone number. Use email only.')
                )
            if (self.auth_provider == 'phone' and self.phone and self.email):
                raise ValidationError(
                    _('Phone auth provider should not have '
                      'an email address. Use phone only.')
                )

            if (self.auth_provider == self.PROVIDER_GOOGLE and not self.email):
                raise ValidationError(
                    _('Google authentication requires an email address.')
                )

            if (self.email and UnifiedUser.objects.filter(email=self.email).exists()):
                raise ValidationError({'email': _('This email is already in use.')})

            if (self.phone and UnifiedUser.objects.filter(phone=self.phone).exists()):
                raise ValidationError({'phone': _('This phone number is already in use.')})

            valid_roles = dict(self.ROLE_CHOICES).keys()
            if self.role not in valid_roles:
                raise ValidationError({
                    'role': _(
                        'Invalid role value. Must be one of: '
                        + ', '.join(valid_roles)
                    )
                })

        else:
            # EXISTING USER — IMMUTABILITY GUARDS
            existing = UnifiedUser.objects.all_with_deleted().get(pk=self.pk)

            if (existing.email is not None and self.email != existing.email):
                raise ValidationError({'email': _('Email cannot be changed after user creation.')})

            if (existing.phone is not None and self.phone != existing.phone):
                raise ValidationError({'phone': _('Phone cannot be changed after user creation.')})

            if self.role != existing.role:
                raise ValidationError({'role': _('Role cannot be changed after user creation.')})

            if self.auth_provider != existing.auth_provider:
                raise ValidationError({
                    'auth_provider': _('Auth provider cannot be changed after user creation.')
                })

            logger.info("Details updated for user: %s", existing.identifying_info)

        return None

    def save(self, *args, **kwargs):
        """Save with validation, NULL normalisation, and member_id auto-generation."""
        if not self.email:
            self.email = None
        if not self.phone:
            self.phone = None
        if not self.avatar:
            self.avatar = None

        if self._state.adding and not self.member_id:
            self.member_id = generate_member_id()

        self.full_clean()
        super().save(*args, **kwargs)
        logger.info(
            "Saved UnifiedUser %s [%s] member_id=%s",
            self.pk, self.auth_provider, self.member_id,
        )

    def is_owner(self, user):
        """Ownership check for HardDeleteMixin."""
        return self.pk == user.pk


# Register with auditlog at module level
try:
    auditlog.register(UnifiedUser)
except Exception:
    pass  # Already registered (during test reloads)
