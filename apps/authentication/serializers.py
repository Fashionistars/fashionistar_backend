import logging
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from phonenumber_field.serializerfields import PhoneNumberField
from django.shortcuts import get_object_or_404
from apps.authentication.models import UnifiedUser # Explicit import for choices if needed

# Get the User model dynamically (should be UnifiedUser)
User = get_user_model()

# Initialize logger for this module
logger = logging.getLogger('application')

class OTPSerializer(serializers.Serializer):
    """
    Serializer for OTP verification with robust validation and error handling.
    """
    otp = serializers.CharField(
        required=True, 
        max_length=6, 
        help_text="One-Time Password (OTP) for verification."
    )

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

    def validate(self, data):
        """
        Authenticates the user based on either email or phone and password, with robust error handling.

        Args:
            data (dict): Input data containing 'email_or_phone' and 'password'.

        Returns:
            dict: Validated data with the 'user' object.

        Raises:
            serializers.ValidationError: On authentication failure.
        """
        try:
            email_or_phone = data.get('email_or_phone')
            password = data.get('password')

            # Efficient lookup using specific fields rather than full scan
            # Note: We filter by is_active=True/False depending on logic, but checking existence first
            # We assume soft delete 'is_deleted' might exist if SoftDeleteModel is used, otherwise ignore
            
            # Using Q objects or simple if/else for email/phone
            user = None
            if '@' in email_or_phone:
                user = User.objects.filter(email=email_or_phone).first()
            else:
                user = User.objects.filter(phone=email_or_phone).first()
            
            if not user:
                # Check 'is_deleted' if strictly required, but usually filter excludes them automatically if manager is set
                logger.warning(f"Login failed: User not found for {email_or_phone}")
                raise serializers.ValidationError({'email_or_phone': [_('User with this email or phone not found.')]})

            if not user.check_password(password):
                logger.warning(f"Login failed: Incorrect password for {email_or_phone}")
                raise serializers.ValidationError({'password': [_('Incorrect password.')]})

            # Check for verification status instead of just is_active if that's the business rule
            # Assuming 'is_active' means they are allowed to login generally
            if not user.is_active:
                logger.warning(f"Login failed: Account not activated for {email_or_phone}")
                raise serializers.ValidationError({'non_field_errors': [_('Account not activated!!!. Check email/phone for OTP.')]})

            logger.info(f"Login validation successful for {email_or_phone}")
            data['user'] = user
            return data

        except serializers.ValidationError as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in login validation: {str(e)}")
            raise serializers.ValidationError({'non_field_errors': [_('An unexpected error occurred during login.')]})


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
    Strictly enforces One-of-Email-or-Phone logic.
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
    
    # Use explicit choices from UnifiedUser if available, else fallback
    ROLE_CHOICES = getattr(UnifiedUser, 'ROLE_CHOICES', [('vendor', 'Vendor'), ('client', 'Client')])
    role = serializers.ChoiceField(
        choices=ROLE_CHOICES, 
        help_text="User's role"
    )

    class Meta:
        model = User
        fields = (
            'email', 'phone', 'role', 'password', 'password2', 
            'bio', 'avatar', 'country', 'state', 'city', 'address'
        )

    def validate(self, attrs):
        """
        Validates registration data with strict checks.
        """
        try:
            # 1. Password Match
            if attrs['password'] != attrs['password2']:
                logger.warning("Registration failed: Passwords do not match.")
                raise serializers.ValidationError({"password": _("Passwords do not match.")})

            email = attrs.get('email')
            phone = attrs.get('phone')
            role = attrs.get('role')

            # 2. Strict Role Validation
            valid_roles = [c[0] for c in self.ROLE_CHOICES]
            if role not in valid_roles:
                logger.warning(f"Registration failed: Invalid role {role}.")
                raise serializers.ValidationError({'role': _("Invalid role value.")})

            # 3. Exclusivity Check (Email XOR Phone)
            # "Please provide either an email address or a phone number, not both."
            if email and phone:
                logger.warning("Registration failed: Both email and phone provided.")
                raise serializers.ValidationError(
                    {'non_field_errors': [_('Please provide either an email address or a phone number, not both.')]}
                )
            
            # 4. Existence Check (At least one)
            if not email and not phone:
                logger.warning("Registration failed: Neither email nor phone provided.")
                raise serializers.ValidationError(
                    {'non_field_errors': [_('Please provide either an email address or a phone number, one is required.')]}
                )

            # 5. Uniqueness Check
            if email and User.objects.filter(email=email).exists():
                logger.warning(f"Registration failed: Email {email} already exists.")
                raise serializers.ValidationError({"email": _("A user with this email already exists.")})

            if phone and User.objects.filter(phone=phone).exists():
                logger.warning(f"Registration failed: Phone {phone} already exists.")
                raise serializers.ValidationError({"phone": _("A user with this phone number already exists.")})

            logger.info("Registration validation successful.")
            return attrs

        except serializers.ValidationError as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in registration validation: {str(e)}")
            raise serializers.ValidationError({"non_field_errors": _("An error occurred during validation.")})

    def create(self, validated_data):
        """
        Creates a new user with merged profile data.
        """
        try:
            email = validated_data.get('email')
            phone = validated_data.get('phone')
            password = validated_data.get('password')
            role = validated_data.get('role')

            # Extract extra fields (bio, country, etc.)
            # These are passed to create_user which should handle extra_fields
            extra_fields = {
                k: v for k, v in validated_data.items() 
                if k not in ['password', 'password2', 'email', 'phone', 'role']
            }

            # Determine Auth Provider
            auth_provider = UnifiedUser.PROVIDER_EMAIL if email else UnifiedUser.PROVIDER_PHONE

            user = User.objects.create_user(
                email=email if email else None,
                phone=phone,
                password=password,
                role=role,
                is_active=False,  # Require verification
                auth_provider=auth_provider,
                **extra_fields
            )
            logger.info(f"New user registered: {user.pk} - {role}")
            return user
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            raise serializers.ValidationError({"error": f"An error occurred during user creation: {e}"})


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
    """
    email_or_phone = serializers.CharField(
        write_only=True, 
        required=True, 
        help_text="User's email or phone for resend OTP"
    )

    def validate(self, data):
        """
        Validates that a user exists for the provided email or phone.
        """
        try:
            email_or_phone = data.get('email_or_phone')
            user = None
            if '@' in email_or_phone:
                user = get_object_or_404(User, email=email_or_phone)
            else:
                user = get_object_or_404(User, phone=email_or_phone)
                
            logger.info(f"Resend OTP validation successful for {email_or_phone}")
            return data
        except Exception as e:
            # get_object_or_404 raises Http404, we want ValidationError
            logger.warning(f"Resend OTP failed: User not found for {data.get('email_or_phone')}")
            raise serializers.ValidationError({'email_or_phone': [_('User with this email or phone not found.')]})


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting password reset.
    """
    email_or_phone = serializers.CharField(
        write_only=True, 
        required=True, 
        help_text="User's email or phone for password reset"
    )

    def validate(self, data):
        """
        Validates user existence.
        """
        try:
            email_or_phone = data.get('email_or_phone')
            if '@' in email_or_phone:
                get_object_or_404(User, email=email_or_phone)
            else:
                get_object_or_404(User, phone=email_or_phone)
            logger.info(f"Password reset request validation successful for {email_or_phone}")
            return data
        except Exception as e:
            logger.warning(f"Password reset request failed: User not found for {data.get('email_or_phone')}")
            raise serializers.ValidationError({'email_or_phone': [_('User with this email or phone not found.')]})


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

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": _("Passwords do not match.")})
        return attrs


class PasswordResetConfirmPhoneSerializer(serializers.Serializer):
    """
    Serializer for confirming password reset via phone.
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
    otp = serializers.CharField(
        required=True, 
        allow_blank=False, 
        max_length=6, 
        help_text="OTP sent to user's phone"
    )

    def validate(self, attrs):
        """
        Validates passwords and OTP.
        """
        try:
            if attrs['password'] != attrs['password2']:
                raise serializers.ValidationError({"password": _("Passwords do not match.")})

            otp = attrs.get('otp')
            if not otp or len(otp) != 6 or not otp.isdigit():
                raise serializers.ValidationError({"otp": _("OTP must be 6 digits and numeric.")})

            return attrs
        except serializers.ValidationError as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in password reset confirm: {str(e)}")
            raise serializers.ValidationError({"non_field_errors": _("Validation failed.")})


class LogoutSerializer(serializers.Serializer):
    """
    Serializer for user logout.
    """
    refresh_token = serializers.CharField(help_text="Refresh token for logout")


class ProtectedUserSerializer(serializers.ModelSerializer):
    """
    Serializer to expose only safe user information.
    Optimized for speed by explicitly listing fields.
    """
    class Meta:
        model = User
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
        model = User
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
