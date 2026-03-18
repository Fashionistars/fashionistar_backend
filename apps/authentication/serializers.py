import logging

from apps.authentication.models import UnifiedUser  # Explicit import for choices if needed
from django.contrib.auth.password_validation import validate_password
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers

# Initialize logger for this module
logger = logging.getLogger(__name__)

class OTPSerializer(serializers.Serializer):
    """
    Serializer for OTP verification with robust validation and error handling.
    """
    otp = serializers.CharField(
        required=True, 
        max_length=6, 
        help_text="One-Time Password (OTP) for verification."
    )

    class Meta:
        ref_name = "AuthOTP"

    def validate(self, attrs):
        """
        Validates the OTP input with strict checks.

        Args:
            attrs (dict): The attributes to validate, containing 'otp'.

        Returns:
            dict: The validated attributes.

        Raises:
            serializers.ValidationError: If OTP is missing, not 6 characters, or not digits.
        """
        try:
            otp = attrs.get('otp')
            if not otp:
                logger.warning("OTP validation failed: OTP is required.")
                raise serializers.ValidationError({"otp": _("OTP is required.")})

            # Validate length
            if len(otp) != 6:
                logger.warning(f"OTP validation failed: Invalid length {len(otp)}.")
                raise serializers.ValidationError({"otp": _("OTP length should be of six digits.")})

            # Validate digits only
            if not otp.isdigit():
                logger.warning("OTP validation failed: Non-digit characters detected.")
                raise serializers.ValidationError({"otp": _("OTP must contain only digits.")})

            logger.info("OTP validation successful.")
            return attrs
        except serializers.ValidationError as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in OTP validation: {str(e)}")
            raise serializers.ValidationError({"otp": _("An error occurred during OTP validation.")})


class AsyncOTPSerializer(OTPSerializer):
    """
    Asynchronous version of OTPSerializer for async validation.
    """
    async def avalidate(self, attrs):
        """
        Asynchronous validation for OTP.
        """
        return self.validate(attrs)


class LoginSerializer(serializers.Serializer):
    """
    Serializer for authenticating users with either email or phone, optimized for speed.
    """
    email_or_phone = serializers.CharField(
        write_only=True, 
        required=True, 
        help_text="User's email or phone for login"
    )
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        help_text="User's password"
    )

    class Meta:
        ref_name = "AuthLogin"

    def validate(self, data):
        """
        Authenticate the user based on email or phone + password.

        Enterprise-grade auth flow (priority order):

        1. Lookup in alive-only manager (is_deleted=False):
           » If found → proceed to password check.
        2. If NOT found in alive-only → lookup in all_with_deleted():
           » If found there AND is_deleted=True → SoftDeletedUserError (403)
           » Else → InvalidCredentialsError (401)
        3. Password check:
           » Wrong password → InvalidCredentialsError (401)
        4a. is_verified check (FIRST — before is_active):
           » is_verified=False → AccountNotVerifiedError (403) with OTP verify/resend URLs
        4b. is_active check (SECOND):
           » is_active=False → AccountDeactivatedError (403) with support URL

        All raised exceptions are DRF APIExceptions (typed), so
        ``LoginView.post()`` catches them individually and returns
        the appropriate HTTP status code.

        Args:
            data (dict): Input containing 'email_or_phone' & 'password'.

        Returns:
            dict: Same data dict with 'user' key added.

        Raises:
            SoftDeletedUserError   (403) — account permanently deactivated.
            AccountNotVerifiedError(403) — account not yet OTP-verified.
            AccountDeactivatedError(403) — is_active=False (admin-disabled).
            InvalidCredentialsError(401) — wrong password or unknown user.
        """
        from apps.authentication.exceptions import (
            SoftDeletedUserError,
            AccountNotVerifiedError,
            AccountDeactivatedError,
            InvalidCredentialsError,
        )

        email_or_phone = data.get('email_or_phone')
        password = data.get('password')

        try:
            # ── Step 1: Alive-only lookup ────────────────────────────────────────
            user = None
            if '@' in email_or_phone:
                user = UnifiedUser.objects.filter(email=email_or_phone).first()
            else:
                user = UnifiedUser.objects.filter(phone=email_or_phone).first()

            if user is None:
                # ── Step 2: Check soft-deleted pool before giving up ──────────
                if '@' in email_or_phone:
                    deleted_user = UnifiedUser.objects.all_with_deleted().filter(
                        email=email_or_phone, is_deleted=True,
                    ).first()
                else:
                    deleted_user = UnifiedUser.objects.all_with_deleted().filter(
                        phone=email_or_phone, is_deleted=True,
                    ).first()

                if deleted_user:
                    logger.warning(
                        "⛔ Login rejected: soft-deleted account '%s'",
                        email_or_phone,
                    )
                    raise SoftDeletedUserError()

                # Truly unknown user — generic 401 (no enumeration)
                logger.warning(
                    "⛔ Login failed: user not found '%s'", email_or_phone,
                )
                raise InvalidCredentialsError()

            # ── Step 3: Password check ──────────────────────────────────────────
            if not user.check_password(password):
                logger.warning(
                    "⛔ Login failed: wrong password for '%s'", email_or_phone,
                )
                raise InvalidCredentialsError()

            # ── Step 4a: OTP verification check (FIRST — before is_active) ─────
            if not user.is_verified:
                logger.warning(
                    "⛔ Login rejected: account not verified '%s'", email_or_phone,
                )
                raise AccountNotVerifiedError()

            # ── Step 4b: Admin deactivation check (SECOND) ──────────────────
            if not user.is_active:
                logger.warning(
                    "⛔ Login rejected: deactivated account '%s'", email_or_phone,
                )
                raise AccountDeactivatedError()

            logger.info(
                "✅ LoginSerializer: valid credentials for '%s'", email_or_phone,
            )
            data['user'] = user
            return data

        except (
            SoftDeletedUserError, AccountNotVerifiedError,
            AccountDeactivatedError, InvalidCredentialsError,
        ):
            # Typed business exceptions — re-raise so LoginView returns correct HTTP code
            raise

        except Exception as exc:
            logger.error(
                "❌ Unexpected error in LoginSerializer.validate(): %s", exc,
                exc_info=True,
            )
            raise serializers.ValidationError(
                {'non_field_errors': [_('An unexpected error occurred during login.')]}
            )


class AsyncLoginSerializer(LoginSerializer):
    """
    Asynchronous version of LoginSerializer for async validation.
    """
    async def avalidate(self, data):
        """
        Asynchronous validation for login.
        """
        # Note: Database calls inside validate need sync_to_async wrapper if running in strictly async context
        # But if calling from async view, separating I/O is better.
        # For now, we assume implicit sync execution or simple reuse.
        return self.validate(data)


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration, handling both email and phone registration with merged Profile fields.
    Strictly enforces One-of-Email-or-Phone logic and delegates creation to Service layer.
    """
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password], 
        style={'input_type': 'password'}, 
        help_text="User's password"
    )
    password2 = serializers.CharField(
        write_only=True, 
        required=True, 
        style={'input_type': 'password'}, 
        help_text="Confirm user's password"
    )
    email = serializers.EmailField(
        required=False, 
        allow_blank=True, 
        help_text="User's email address"
    )
    phone = PhoneNumberField(
        required=False, 
        allow_blank=True, 
        help_text="User's phone number"
    )
    
    # Public registration only allows vendor or client roles.
    # Admin / staff / editor are internal roles assigned via admin panel.
    ROLE_CHOICES = [('vendor', 'Vendor'), ('client', 'Client')]
    role = serializers.ChoiceField(
        choices=ROLE_CHOICES,
        help_text="User's role: 'vendor' or 'client'"
    )

    class Meta:
        model = UnifiedUser
        fields = (
            'email', 'phone', 'role', 'password', 'password2'
        )
        ref_name = "AuthUserRegistration"

    def validate(self, attrs):
        """
        Validates registration data with strict checks.

        KEY FIX: Normalises empty-string email/phone to None BEFORE any
        downstream check. DRF inserts '' for optional fields not in the
        payload (because allow_blank=True). Without this normalisation,
        email='' is forwarded to the service and ultimately to the DB
        unique constraint — causing a false "Email already exists" error
        on every second phone-only registration.
        """
        try:
            # 1. Password Match
            if attrs['password'] != attrs['password2']:
                logger.warning("Registration failed: Passwords do not match.")
                raise serializers.ValidationError(
                    {"password": _("Passwords do not match.")}
                )

            # ── CRITICAL: Normalise empty strings → None ──────────────────
            # If the client omits 'email' entirely, DRF sets email='' due
            # to allow_blank=True. '' passed to create_user() hits the DB
            # unique constraint on email as if a real duplicate was sent.
            # Converting '' → None here prevents the false "email exists" error
            # that was firing on every phone-only registration.
            attrs['email'] = attrs.get('email') or None
            attrs['phone'] = attrs.get('phone') or None

            email = attrs['email']
            phone = attrs['phone']
            role = attrs.get('role')

            # 2. Strict Role Validation
            valid_roles = [c[0] for c in self.ROLE_CHOICES]
            if role not in valid_roles:
                logger.warning("Registration failed: Invalid role %s.", role)
                raise serializers.ValidationError(
                    {'role': _("Invalid role. Must be 'vendor' or 'client'.")}
                )

            # 3. Exclusivity Check — Email XOR Phone (not both)
            if email and phone:
                logger.warning("Registration failed: Both email and phone provided.")
                raise serializers.ValidationError({
                    'non_field_errors': [_(
                        'Please provide either an email address or a '
                        'phone number, not both.'
                    )]
                })

            # 4. Presence Check — at least one identifier required
            if not email and not phone:
                logger.warning("Registration failed: Neither email nor phone provided.")
                raise serializers.ValidationError({
                    'non_field_errors': [_(
                        'Please provide either an email address or a '
                        'phone number; one is required.'
                    )]
                })

            # ── Normalise email to match manager's normalize_email() ─────────
            # BaseUserManager.normalize_email() lowercases the domain part.
            # Without this, 'user@EXAMPLE.COM' passes the serializer's
            # filter(email='user@EXAMPLE.COM') check (→ not found, because
            # the DB stores 'user@example.com') and only fails at
            # model.full_clean() — causing the noisy 1900ms WSGI path.
            # Normalizing here ensures the serializer check matches the DB.
            from django.contrib.auth.base_user import BaseUserManager as _BUM
            if email:
                email = _BUM.normalize_email(email)
                attrs['email'] = email

            # ── 5. Soft-deleted pool check FIRST ─────────────────────────────
            # CRITICAL ORDER: We MUST check soft-deleted users BEFORE the
            # standard alive-only uniqueness check. If a soft-deleted user
            # exists with the same email/phone, the CustomUserManager will
            # only see alive users (is_deleted=False) and won't catch it,
            # causing the UNIQUE constraint to fire at the DB layer (500 error).
            # By catching it here we return the correct 403 + support message.
            from apps.authentication.exceptions import SoftDeletedUserExistsError

            if email:
                soft_deleted_by_email = UnifiedUser.objects.all_with_deleted().filter(
                    email__iexact=email, is_deleted=True
                ).first()
                if soft_deleted_by_email:
                    logger.warning(
                        "⛔ Registration blocked: soft-deleted account for email '%s'", email
                    )
                    raise SoftDeletedUserExistsError()

            if phone:
                soft_deleted_by_phone = UnifiedUser.objects.all_with_deleted().filter(
                    phone=phone, is_deleted=True
                ).first()
                if soft_deleted_by_phone:
                    logger.warning(
                        "⛔ Registration blocked: soft-deleted account for phone '%s'", phone
                    )
                    raise SoftDeletedUserExistsError()

            # ── 6. Active Uniqueness Check — catches live duplicates BEFORE model.save()
            #    Uses iexact for full case-insensitive safety on both WSGI+ASGI.
            if email and UnifiedUser.objects.filter(
                email__iexact=email
            ).exists():
                logger.warning(
                    "Registration failed: Email %s already exists.", email
                )
                raise serializers.ValidationError(
                    {"email": _("A user with this email address already exists.")}
                )

            if phone and UnifiedUser.objects.filter(phone=phone).exists():
                logger.warning(
                    "Registration failed: Phone %s already exists.", phone
                )
                raise serializers.ValidationError(
                    {"phone": _("A user with this phone number already exists.")}
                )

            logger.info("Registration validation successful.")
            return attrs

        except (serializers.ValidationError, SoftDeletedUserExistsError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in registration validation: {str(e)}")
            raise serializers.ValidationError({"non_field_errors": _("An error occurred during validation.")})

    def create(self, validated_data):
        """
        Creates a new user via RegistrationService (Sync).

        This method delegates user creation to the centralized RegistrationService,
        which handles atomic transactions, OTP generation, and notification dispatch.
        It strips non-model fields (password2/password_confirm) before forwarding.

        Args:
            validated_data (dict): Validated registration data from DRF validation.

        Returns:
            UnifiedUser: The newly created user instance.

        Raises:
            serializers.ValidationError: If user creation fails for any reason.
        """
        try:
            from apps.authentication.services.registration_service import (
                RegistrationService,
            )

            # ── Strip non-model fields before forwarding to service ──────
            # password2/password_confirm are validation-only; the service
            # only needs the canonical 'password' field.
            validated_data.pop('password2', None)
            validated_data.pop('password_confirm', None)

            # ── Delegate to RegistrationService (atomic, OTP, Email/SMS) ─
            # Pass validated_data directly — it already contains email,
            # phone, password, role. No duplicate kwargs.
            result = RegistrationService.register_sync(**validated_data)

            # ── Retrieve created user instance for serializer.save() ─────
            from apps.authentication.models import UnifiedUser
            user = UnifiedUser.objects.get(id=result['user_id'])

            logger.info(
                f"✅ User created via serializer: {user.email or user.phone} "
                f"(ID: {user.id}, Role: {user.role})"
            )
            return user

        except Exception as e:
            logger.error(f"❌ Error creating user via serializer: {str(e)}", exc_info=True)
            raise serializers.ValidationError(
                {"error": f"An error occurred during user creation: {e}"}
            )


class AsyncUserRegistrationSerializer(UserRegistrationSerializer):
    """
    Asynchronous version of UserRegistrationSerializer.
    """
    async def acreate(self, validated_data):
        """
        Asynchronous user creation.
        """
        return self.create(validated_data)


class ResendOTPRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting OTP resend by email or phone.

    CRITICAL FIX: Uses ``all_with_deleted()`` manager so that users who
    just registered (is_active=False, is_verified=False) are found.
    The default ``objects`` manager filters alive-only (is_deleted=False)
    but a newly-registered unverified user IS alive — they just haven't
    been activated yet. Using ``all_with_deleted()`` is the correct choice
    here because it returns ALL rows regardless of soft-delete or active state.
    """
    email_or_phone = serializers.CharField(
        write_only=True,
        required=True,
        help_text="User's email or phone for resend OTP"
    )

    class Meta:
        ref_name = "AuthResendOTPRequest"

    def validate(self, data):
        """
        Validates that a user exists for the provided email or phone.
        Uses all_with_deleted() so recently-registered unverified users
        are found (they are NOT soft-deleted, just not yet active).
        """
        try:
            email_or_phone = data.get('email_or_phone')
            user = None

            # Use all_with_deleted() — includes active, inactive, and
            # soft-deleted users. This is correct for resend-OTP because
            # the user just registered and may not be active yet.
            if '@' in email_or_phone:
                user = UnifiedUser.objects.all_with_deleted().filter(
                    email=email_or_phone
                ).first()
            else:
                user = UnifiedUser.objects.all_with_deleted().filter(
                    phone=email_or_phone
                ).first()

            if not user:
                logger.warning(
                    "ResendOTP validation failed: no user for '%s'", email_or_phone
                )
                raise serializers.ValidationError({
                    'email_or_phone': [_(
                        'No account found with this email or phone. '
                        'Please check your input or register a new account.'
                    )]
                })

            # Store user on validated_data for the view to access
            data['user'] = user
            logger.info("ResendOTP validation successful for %s", email_or_phone)
            return data

        except serializers.ValidationError:
            raise
        except Exception as exc:
            logger.warning(
                "ResendOTP failed for %s: %s",
                data.get('email_or_phone'), exc
            )
            raise serializers.ValidationError({
                'email_or_phone': [_('User with this email or phone not found.')]
            })


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting password reset.
    Uses all_with_deleted() so soft-deleted users can still trigger a reset
    (anti-enumeration: always returns 200 regardless).
    """
    email_or_phone = serializers.CharField(
        write_only=True,
        required=True,
        help_text="User's email or phone for password reset"
    )

    class Meta:
        ref_name = "AuthPasswordResetRequest"

    def validate(self, data):
        """
        Validates user existence — uses all_with_deleted() for consistency.
        Returns success even if user not found (anti-enumeration).
        """
        try:
            email_or_phone = data.get('email_or_phone')
            if '@' in email_or_phone:
                UnifiedUser.objects.all_with_deleted().filter(
                    email=email_or_phone
                ).first()  # Anti-enumeration: ignore None
            else:
                UnifiedUser.objects.all_with_deleted().filter(
                    phone=email_or_phone
                ).first()  # Anti-enumeration: ignore None
            logger.info("Password reset request validation for %s", email_or_phone)
            return data
        except Exception as exc:
            logger.warning(
                "Password reset request error for %s: %s",
                data.get('email_or_phone'), exc
            )
            return data  # Always pass — anti-enumeration


class PasswordResetConfirmEmailSerializer(serializers.Serializer):
    """
    Serializer for confirming password reset via email.
    """
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password], 
        help_text="New password"
    )
    password2 = serializers.CharField(
        write_only=True, 
        required=True, 
        help_text="Confirm new password"
    )

    class Meta:
        ref_name = "AuthPasswordResetConfirmEmail"

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": _("Passwords do not match.")})
        return attrs


class PasswordResetConfirmPhoneSerializer(serializers.Serializer):
    """
    Serializer for confirming password reset via phone OTP.

    Requires phone number in body so the service can look up the user
    and validate the OTP against their Redis-stored token.
    """
    # phone = serializers.CharField(
    #     required=True,
    #     help_text="The user's registered phone number (E.164 format)."                WE DON'T NEED THIS RIGHT NOW, WE ONLY NEED OTP SO THAT IF THE OTP IS CORRECT, WE CAN FETCH THE USER'S PHONE NUMBER FROM THE OTP TOKEN IN REDIS AND THEN RESET THE PASSWORD 
    # )
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        help_text="New password"
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Confirm new password"
    )
    otp = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=6,
        help_text="OTP sent to user's phone"
    )

    class Meta:
        ref_name = "AuthPasswordResetConfirmPhone"

    def validate(self, attrs):
        """
        Validates passwords and OTP format.
        On invalid OTP format, returns rich error with resend/reset URLs.
        """
        try:
            from django.conf import settings as _s
            _base = getattr(_s, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')

            if attrs['password'] != attrs['password2']:
                raise serializers.ValidationError({"password": _("Passwords do not match.")})

            otp = attrs.get('otp')
            if not otp or len(otp) != 6 or not otp.isdigit():
                raise serializers.ValidationError({
                    "otp": _(
                        "OTP must be 6 numeric digits. "
                        "Didn't receive it? Request a new one or re-trigger the reset."
                    ),
                    "resend_otp_url": f"{_base}/resend-otp",
                    "reset_request_url": "/api/v1/password/reset-request/",
                })

            return attrs
        except serializers.ValidationError as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in password reset confirm phone: {str(e)}")
            raise serializers.ValidationError({"non_field_errors": _("Validation failed.")})


class LogoutSerializer(serializers.Serializer):
    """
    Serializer for user logout.
    Accepts the refresh token body so the server can blacklist it.

    Note: The field is named 'refresh' (not 'refresh_token') to match
    the SimpleJWT convention used in LogoutView.post().
    """
    refresh = serializers.CharField(
        required=True,
        help_text="Refresh token to blacklist on logout.",
    )

    class Meta:
        ref_name = "AuthLogout"


class TokenRefreshSerializer(serializers.Serializer):
    """
    Serializer for JWT token refresh.

    Wraps SimpleJWT's token refresh so drf-yasg can generate the correct
    Swagger schema for RefreshTokenView (field: refresh → returns access).
    """
    refresh = serializers.CharField(
        required=True,
        help_text="A valid refresh token previously issued by the login endpoint.",
    )

    class Meta:
        ref_name = "AuthTokenRefresh"


class ProtectedUserSerializer(serializers.ModelSerializer):
    """
    Serializer to expose only safe user information.
    Optimized for speed by explicitly listing fields.
    """
    class Meta:
        model = UnifiedUser
        fields = (
            'id', 'email', 'phone', 'role', 
            'is_active', 'is_verified', 
            'bio', 'avatar', 'country', 'city', 'state', 'address'
        )
        ref_name = "AuthProtectedUser"


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Full Profile Serializer.
    Includes all fields minus internal ones.
    """
    class Meta:
        model = UnifiedUser
        fields = '__all__'
        read_only_fields = ('id', 'password', 'last_login', 'is_superuser', 'is_staff', 'groups', 'user_permissions')
        extra_kwargs = {
            'password': {'write_only': True}
        }

class GoogleAuthSerializer(serializers.Serializer):
    """
    Serializer for Google authentication input.
    """
    id_token = serializers.CharField(required=True, help_text="Google ID Token")
    
    # Use explicit choices
    ROLE_CHOICES = getattr(UnifiedUser, 'ROLE_CHOICES', [('vendor', 'Vendor'), ('client', 'Client')])
    role = serializers.ChoiceField(
        choices=ROLE_CHOICES, 
        default='client', 
        help_text="User's role"
    )

    class Meta:
        ref_name = "AuthGoogleAuth"

    def validate(self, attrs):
        try:
            id_token = attrs.get('id_token')
            if not id_token:
                raise serializers.ValidationError({"id_token": _("Google ID Token is required.")})

            role = attrs.get('role')
            valid_roles = [c[0] for c in self.ROLE_CHOICES]
            if role not in valid_roles:
                raise serializers.ValidationError({"role": _("Invalid role.")})

            return attrs
        except serializers.ValidationError as e:
            raise e
        except Exception as e:
             logger.error(f"Google auth validation error: {str(e)}")
             raise serializers.ValidationError({"non_field_errors": _("An error occurred during Google Auth validation.")})


class PasswordChangeSerializer(serializers.Serializer):
    """
    Serializer for changing password when logged in.
    """
    old_password = serializers.CharField(write_only=True, required=True, help_text="Current password")
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password], help_text="New password")
    confirm_password = serializers.CharField(write_only=True, required=True, help_text="Confirm new password")

    def validate(self, attrs):
        try:
            if attrs['new_password'] != attrs['confirm_password']:
                raise serializers.ValidationError({"new_password": _("New passwords do not match.")})

            # Check old password if context has request user
            request = self.context.get('request')
            if request and request.user:
                if not request.user.check_password(attrs['old_password']):
                     raise serializers.ValidationError({"old_password": _("Incorrect old password.")})
            
            return attrs
        except serializers.ValidationError as e:
            raise e
        except Exception as e:
            logger.error(f"Password change validation error: {str(e)}")
            raise serializers.ValidationError({"non_field_errors": _("An error occurred during password change.")})

# Alias for standard usage
UserSerializer = UserProfileSerializer
