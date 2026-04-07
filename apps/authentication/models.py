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
        max_value = 10 ** MEMBER_ID_DIGITS - 1  # 9999

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
    Example: ``FASTAR000001``, ``FASTAR000062``, ``FASTAR0001337``

    The counter is sourced from ``MemberIDCounter.next_value()``
    which uses row-level locking (``SELECT FOR UPDATE``) to
    guarantee uniqueness under concurrent writes.

    Returns:
        str: A 10-character uppercase string.
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
    # ``member_id`` is the user-facing identity code displayed
    # on dashboards and support tickets.  The internal UUID
    # ``id`` remains the actual primary key and is used for all
    # API requests and relational lookups.
    #
    # Format  : FASTAR0001  (prefix + 6 zero-padded digits)
    # Length  : 10 characters, always uppercase
    # Pattern : FASTAR[0001-9999]
    # Mutable : NO — locked after first generation in save()
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

        IMPORTANT — NULL re-normalisation after super().clean():
        ``AbstractUser.clean()`` calls ``BaseUserManager.normalize_email()``
        which converts ``None`` → ``''`` (empty string).
        Example: ``normalize_email(None)`` → ``email or ''`` → ``''``
        This OVERWRITES the ``email = None`` we set in ``save()`` just
        before calling ``full_clean()``, causing Django's
        ``validate_unique()`` to treat ``email=''`` as a real duplicate
        and raise "Unified User with this Email address already exists."
        for every second phone-only registration.

        We re-apply None normalisation here to reverse that silently.
        """
        super().clean()

        # ── Re-apply NULL normalisation (undoes AbstractUser.clean() side-effect)
        # Must happen BEFORE validate_unique() which is called by full_clean()
        # after clean() returns.
        if not self.email:
            self.email = None
        if not self.phone:
            self.phone = None

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
        Save with validation, NULL normalisation, and member_id
        auto-generation.

        On first creation (``_state.adding`` is True), generates
        a unique ``member_id`` via the atomic counter before
        persisting.  On subsequent saves the existing value is
        preserved — ``editable=False`` and the form's
        ``get_readonly_fields`` prevent UI modification.

        .. important::
            NULL normalisation MUST happen before ``full_clean()``
            and before ``super().save()`` to prevent Django's
            unique-constraint check from treating an empty string
            as a duplicate phone/email across multiple users.
        """
        # ── 1. Normalize empty strings → NULL (MUST be first) ──
        # PhoneNumberField and EmailField can receive '' (empty
        # string) from admin forms when the field is left blank.
        # PostgreSQL treats '' != NULL for unique constraints, but
        # SQLite can still hit UNIQUE violations on ''. Normalize
        # to NULL here so the DB always gets None when blank.
        if not self.email:
            self.email = None
        if not self.phone:
            self.phone = None
        # URLField rejects '' (empty string) as invalid URL.
        # Normalize to None so blank avatar passes validation.
        if not self.avatar:
            self.avatar = None

        # ── 2. Auto-generate member_id exactly once at creation ─
        if self._state.adding and not self.member_id:
            self.member_id = generate_member_id()

        # ── 3. Full model validation ────────────────────────────
        self.full_clean()

        # ── 4. Persist ─────────────────────────────────────────
        super().save(*args, **kwargs)
        logger.info(
            "Saved UnifiedUser %s [%s] member_id=%s",
            self.pk,
            self.auth_provider,
            self.member_id,
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


# ================================================================
# LOGIN EVENT — Binance-style security audit log
# Every single login attempt (success OR failure) is recorded here.
# Displayed as "Recent Login Activity" in the user security dashboard.
# ================================================================

class LoginEvent(TimeStampedModel):
    """
    Immutable security audit record for every login **attempt**.

    Modelled after the security audit logs used by Binance, Coinbase,
    Telegram, and Google — capturing the minimum viable set of forensic
    data needed for:
      - User-visible "recent logins" in the Security Dashboard
      - SIEM / threat-detection pipelines
      - Suspicious-activity alerting (new country, new device, etc.)
      - Compliance and audit trails

    Design decisions:
      - ``user`` is nullable so we can log failed attempts for
        *unknown* identifiers (user enumeration attempts).
      - ``is_successful`` + ``failure_reason`` let us distinguish
        wrong-password from inactive-account from deactivated-account
        in a single table scan.
      - ``risk_score`` (0–100) is updated by a Celery task after
        the request completes (geo-lookup + device fingerprint).
      - ``ip_address`` uses ``GenericIPAddressField`` to support both
        IPv4 and IPv6 natively.
      - The model is intentionally **append-only** — no update() calls.
        Audit records must never be mutated.
    """

    # ── Outcomes ─────────────────────────────────────────────────────
    OUTCOME_SUCCESS  = 'success'
    OUTCOME_FAILED   = 'failed'
    OUTCOME_BLOCKED  = 'blocked'    # IP-banned or rate-limited
    OUTCOME_SUSPICIOUS = 'suspicious'  # MFA challenged

    OUTCOME_CHOICES = [
        (OUTCOME_SUCCESS,   'Success'),
        (OUTCOME_FAILED,    'Failed'),
        (OUTCOME_BLOCKED,   'Blocked'),
        (OUTCOME_SUSPICIOUS,'Suspicious'),
    ]

    # ── Device / client types ─────────────────────────────────────────
    CLIENT_WEB    = 'web'
    CLIENT_MOBILE = 'mobile'
    CLIENT_API    = 'api'
    CLIENT_CURL   = 'curl'
    CLIENT_UNKNOWN = 'unknown'

    CLIENT_TYPE_CHOICES = [
        (CLIENT_WEB,    'Web Browser'),
        (CLIENT_MOBILE, 'Mobile App'),
        (CLIENT_API,    'API Client'),
        (CLIENT_CURL,   'cURL / Script'),
        (CLIENT_UNKNOWN,'Unknown'),
    ]

    # ── Auth methods ──────────────────────────────────────────────────
    METHOD_EMAIL   = 'email'
    METHOD_PHONE   = 'phone'
    METHOD_GOOGLE  = 'google'
    METHOD_BIOMETRIC = 'biometric'

    METHOD_CHOICES = [
        (METHOD_EMAIL,    'Email + Password'),
        (METHOD_PHONE,    'Phone + Password'),
        (METHOD_GOOGLE,   'Google OAuth'),
        (METHOD_BIOMETRIC,'Biometric / FIDO2'),
    ]

    # ── Core relations ───────────────────────────────────────────────
    user = models.ForeignKey(
        UnifiedUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='login_events',
        db_index=True,
        help_text=(
            "NULL when a login attempt targets an unknown identifier "
            "(failed user-enumeration attempt)."
        ),
    )

    # ── Request metadata ──────────────────────────────────────────────
    ip_address = models.GenericIPAddressField(
        protocol='both',          # IPv4 + IPv6
        unpack_ipv4=True,         # ::ffff:1.2.3.4 → 1.2.3.4
        db_index=True,
        help_text="Client IP address (supports IPv4 and IPv6).",
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Raw HTTP User-Agent string.",
    )

    # ── Parsed device info (populated by Celery post-request) ─────────
    client_type = models.CharField(
        max_length=20,
        choices=CLIENT_TYPE_CHOICES,
        default=CLIENT_UNKNOWN,
        db_index=True,
        help_text="Derived from User-Agent: web / mobile / api / curl.",
    )
    browser_family = models.CharField(
        max_length=100,
        blank=True,
        help_text="Browser family: Chrome, Firefox, Safari, Unknown, etc.",
    )
    os_family = models.CharField(
        max_length=100,
        blank=True,
        help_text="Operating system: Windows, macOS, iOS, Android, Linux, etc.",
    )
    device_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Device category: desktop, mobile, tablet, bot, etc.",
    )

    # ── Geolocation (populated by Celery geo-lookup task) ─────────────
    country = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Country name derived from IP (via MaxMind / ipapi).",
    )
    country_code = models.CharField(
        max_length=3,
        blank=True,
        help_text="ISO 3166-1 alpha-2 country code (e.g. 'NG', 'US').",
    )
    region = models.CharField(
        max_length=100,
        blank=True,
        help_text="State / region / province (e.g. 'Lagos', 'California').",
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        help_text="City name (e.g. 'Lagos', 'San Francisco').",
    )
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True,
        help_text="Approx. latitude from IP geo-lookup.",
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True,
        help_text="Approx. longitude from IP geo-lookup.",
    )

    # ── Auth context ──────────────────────────────────────────────────
    auth_method = models.CharField(
        max_length=20,
        choices=METHOD_CHOICES,
        default=METHOD_EMAIL,
        help_text="Authentication method used for this attempt.",
    )
    outcome = models.CharField(
        max_length=20,
        choices=OUTCOME_CHOICES,
        default=OUTCOME_FAILED,
        db_index=True,
        help_text="Result of the login attempt.",
    )
    failure_reason = models.CharField(
        max_length=100,
        blank=True,
        help_text=(
            "Short machine-readable failure code: "
            "'invalid_credentials', 'account_inactive', 'account_deleted', "
            "'rate_limited', 'mfa_required', etc."
        ),
    )
    is_successful = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True iff the login attempt succeeded and tokens were issued.",
    )

    # ── Risk & Anomaly ────────────────────────────────────────────────
    risk_score = models.SmallIntegerField(
        default=0,
        help_text=(
            "Risk score 0-100. Computed by Celery after the request: "
            "new country (+30), new device (+20), Tor exit node (+50), "
            "high-velocity (+40), etc. ≥70 triggers a security alert."
        ),
    )
    is_new_device = models.BooleanField(
        default=False,
        help_text="True if this is the first time this device fingerprint was seen.",
    )
    is_new_country = models.BooleanField(
        default=False,
        help_text="True if the login country is new for this user.",
    )
    is_tor_exit_node = models.BooleanField(
        default=False,
        help_text="True if the IP is a known Tor exit node.",
    )

    # ── Session link ──────────────────────────────────────────────────
    session = models.ForeignKey(
        'UserSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='login_events',
        help_text="The session created by this successful login (if any).",
    )

    # ── Timestamps ────────────────────────────────────────────────────
    # ``created_at`` from TimeStampedModel = the exact moment of the attempt.

    class Meta:
        verbose_name        = "Login Event"
        verbose_name_plural = "Login Events"
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=['user', '-created_at'],     name='le_user_ts_idx'),
            models.Index(fields=['ip_address', '-created_at'],name='le_ip_ts_idx'),
            models.Index(fields=['outcome', '-created_at'],  name='le_outcome_ts_idx'),
            models.Index(fields=['country', '-created_at'],  name='le_country_ts_idx'),
            models.Index(fields=['is_successful'],            name='le_success_idx'),
        ]

    def __str__(self):
        identifier = (
            str(self.user.email or self.user.phone)
            if self.user else 'anon'
        )
        return (
            f"[{self.outcome.upper()}] {identifier} "
            f"from {self.ip_address} ({self.country or '?'}) "
            f"at {self.created_at:%Y-%m-%d %H:%M:%S UTC}"
        )

    @classmethod
    def record(
        cls,
        *,
        user=None,
        ip_address: str,
        user_agent: str = '',
        auth_method: str = 'email',
        outcome: str = 'failed',
        failure_reason: str = '',
        is_successful: bool = False,
        session=None,
    ) -> 'LoginEvent':
        """
        Factory class-method for creating a LoginEvent in a single call.

        Designed to be called from LoginView immediately after the
        authentication decision is made. Geo-lookup and device parsing
        are deferred to a Celery task (``enrich_login_event``) that
        runs after the HTTP response is sent.

        Usage::

            event = LoginEvent.record(
                user=user,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                auth_method='email',
                outcome=LoginEvent.OUTCOME_SUCCESS,
                is_successful=True,
                session=session,
            )
        """
        return cls.objects.create(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            auth_method=auth_method,
            outcome=outcome,
            failure_reason=failure_reason,
            is_successful=is_successful,
            session=session,
        )


# ================================================================
# USER SESSION — Telegram-style active sessions registry
# One row per live refresh token. "Active sessions" dashboard
# reads from this table. "Log out all other devices" deletes rows.
# ================================================================

class UserSession(TimeStampedModel):
    """
    Tracks every active **authenticated session** (one per refresh token).

    This is the SERVER-SIDE session registry — conceptually similar to
    Telegram's "Active Sessions", GitHub's "Sessions", or Google's
    "Devices this account is signed in to".

    Key capabilities enabled by this model:
      1. **Enumerate active sessions** — ``GET /api/v1/auth/sessions/``
         returns all of the user's live sessions: device, location, last-used.
      2. **Revoke a specific session** — ``DELETE /api/v1/auth/sessions/{id}/``
         deletes the row AND blacklists the JWT refresh token.
      3. **Logout all other devices** — ``POST /api/v1/auth/sessions/revoke-others/``
         deletes all rows except the current one AND blacklists all their tokens.

    Session lifecycle:
      created:    at successful login / Google OAuth / OTP verification
      refreshed:  ``last_used_at`` updated on every token refresh call
      terminated: deleted on explicit logout OR when the refresh token expires

    Relationship to JWT:
      The ``jti`` (JWT ID) of the **refresh token** is the natural key.
      When a user calls ``/logout/``, we:
        1. Blacklist the JTI via SimpleJWT's token blacklist.
        2. Delete the corresponding ``UserSession`` row.
    """

    # ── Device / client types  (mirrors LoginEvent) ───────────────────
    CLIENT_WEB     = 'web'
    CLIENT_MOBILE  = 'mobile'
    CLIENT_API     = 'api'
    CLIENT_UNKNOWN = 'unknown'

    CLIENT_TYPE_CHOICES = [
        (CLIENT_WEB,    'Web Browser'),
        (CLIENT_MOBILE, 'Mobile App'),
        (CLIENT_API,    'API Client'),
        (CLIENT_UNKNOWN,'Unknown'),
    ]

    # ── Core ──────────────────────────────────────────────────────────
    user = models.ForeignKey(
        UnifiedUser,
        on_delete=models.CASCADE,
        related_name='sessions',
        db_index=True,
        help_text="The owner of this session.",
    )
    jti = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text=(
            "JWT ID (jti claim) of the refresh token for this session. "
            "Used to match and blacklist via SimpleJWT."
        ),
    )

    # ── Device information ────────────────────────────────────────────
    client_type = models.CharField(
        max_length=20,
        choices=CLIENT_TYPE_CHOICES,
        default=CLIENT_UNKNOWN,
        help_text="Browser / mobile app / API client.",
    )
    browser_family = models.CharField(
        max_length=100,
        blank=True,
        help_text="Chrome, Firefox, Safari, etc.",
    )
    os_family = models.CharField(
        max_length=100,
        blank=True,
        help_text="Windows, macOS, iOS, Android, Linux, etc.",
    )
    device_name = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Human-readable label for the session, e.g. "
            "'Chrome on Windows', 'iPhone 15 Pro Max', 'cURL Script'."
        ),
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Raw User-Agent string for the session.",
    )

    # ── Geolocation ───────────────────────────────────────────────────
    ip_address = models.GenericIPAddressField(
        protocol='both',
        unpack_ipv4=True,
        null=True, blank=True,
        help_text="IP address at session creation (login time).",
    )
    country = models.CharField(max_length=100, blank=True)
    country_code = models.CharField(max_length=3, blank=True)
    city = models.CharField(max_length=100, blank=True)

    # ── Activity ──────────────────────────────────────────────────────
    last_used_at = models.DateTimeField(
        auto_now=True,
        help_text="Updated on every token refresh. Stale sessions = last_used_at old.",
    )
    expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the refresh token expires (from JWT payload).",
    )
    is_current = models.BooleanField(
        default=False,
        help_text=(
            "True for the session that corresponds to the JWT making "
            "the current request. Computed at serializer time, not stored."
        ),
    )

    class Meta:
        verbose_name        = "User Session"
        verbose_name_plural = "User Sessions"
        ordering            = ["-last_used_at"]
        indexes = [
            models.Index(fields=['user', '-last_used_at'],  name='us_user_ts_idx'),
            models.Index(fields=['jti'],                     name='us_jti_idx'),
            models.Index(fields=['expires_at'],              name='us_expires_idx'),
        ]

    def __str__(self):
        return (
            f"{self.user} — {self.device_name or self.client_type} "
            f"({self.city or self.country or self.ip_address or '?'})"
        )

    @classmethod
    def create_from_token(
        cls,
        *,
        user,
        refresh_token,
        request=None,
    ) -> 'UserSession':
        """
        Create a new session record from a SimpleJWT RefreshToken instance.

        Called immediately after a successful login / Google OAuth / OTP
        verification. IP and User-Agent are extracted from the request.

        Args:
            user:           The authenticated UnifiedUser.
            refresh_token:  A ``rest_framework_simplejwt.tokens.RefreshToken``
                            instance (already issued).
            request:        The Django HttpRequest (for IP + User-Agent).

        Returns:
            The newly-created ``UserSession`` instance.
        """
        import datetime

        from django.utils import timezone

        ip_address = None
        user_agent = ''
        if request:
            forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
            ip_address = (
                forwarded.split(',')[0].strip()
                if forwarded
                else request.META.get('REMOTE_ADDR')
            )
            user_agent = request.META.get('HTTP_USER_AGENT', '')

        jti        = str(refresh_token.payload.get('jti', ''))
        expires_at = timezone.now() + datetime.timedelta(
            seconds=int(refresh_token.lifetime.total_seconds())
        )

        # Build a readable device label from User-Agent
        device_name = 'Unknown Device'
        try:
            import user_agents as ua_parser
            ua = ua_parser.parse(user_agent)
            browser = ua.browser.family
            os_name = ua.os.family
            device_name = f"{browser} on {os_name}" if browser != 'Other' else os_name
        except Exception:
            pass

        return cls.objects.create(
            user=user,
            jti=jti,
            user_agent=user_agent,
            device_name=device_name,
            ip_address=ip_address,
            expires_at=expires_at,
        )



# ================================================================
# CLIENT PROFILE — 1:1 Profile for role='client' users
# ================================================================

class ClientProfile(TimeStampedModel):
    """
    Extended profile for client-role users.
    Linked 1:1 to UnifiedUser (role='client').
    Mirrors the VendorProfile design pattern.
    """
    user = models.OneToOneField(
        "authentication.UnifiedUser",
        on_delete=models.CASCADE,
        related_name="client_profile",
        limit_choices_to={"role": "client"},
        help_text="The client user this profile belongs to.",
    )
    bio = models.TextField(blank=True, default="", max_length=500)
    default_shipping_address = models.TextField(blank=True, default="")
    state   = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="Nigeria")
    SIZE_CHOICES = [
        ("XS","XS"),("S","S"),("M","M"),("L","L"),
        ("XL","XL"),("XXL","XXL"),("XXXL","XXXL"),
    ]
    preferred_size     = models.CharField(max_length=10, choices=SIZE_CHOICES, blank=True, default="")
    style_preferences  = models.JSONField(default=list, blank=True)
    favourite_colours  = models.JSONField(default=list, blank=True)
    total_orders       = models.PositiveIntegerField(default=0)
    total_spent_ngn    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_profile_complete = models.BooleanField(default=False)

    class Meta:
        verbose_name        = "Client Profile"
        verbose_name_plural = "Client Profiles"
        db_table            = "authentication_client_profile"
        indexes = [
            models.Index(fields=["user"], name="client_profile_user_idx"),
        ]

    def __str__(self):
        return f"ClientProfile({self.user.email or self.user.phone or self.user.pk})"

    def update_completeness(self):
        complete = all([self.preferred_size, self.default_shipping_address, bool(self.style_preferences)])
        if self.is_profile_complete != complete:
            self.is_profile_complete = complete
            self.save(update_fields=["is_profile_complete", "updated_at"])

    @classmethod
    def get_or_create_for_user(cls, user):
        profile, _ = cls.objects.get_or_create(user=user)
        return profile
