from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from phonenumber_field.serializerfields import PhoneNumberField
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from userauths.models import Profile

User = get_user_model()


class OTPSerializer(serializers.Serializer):
    """
    Serializer for OTP verification.
    """
    otp = serializers.CharField(required=True, max_length=6)

    def validate(self, attrs):
        """
        Validate the OTP.

        Args:
            attrs (dict): The attributes to validate.

        Returns:
            dict: The validated attributes.

        Raises:
            serializers.ValidationError: If OTP is missing or not 6 characters.
        """
        otp = attrs.get('otp')
        if not otp:
            raise serializers.ValidationError({"otp": "OTP is required."})

        # Validate if OTP is 6 char
        if not (len(otp) == 6):
            raise serializers.ValidationError({"otp": "OTP length should be of six digits."})

        if not otp.isdigit():
            raise serializers.ValidationError({"otp": "OTP must contain only digits."})

        return attrs







class LoginSerializer(serializers.Serializer):
    """
    Serializer for authenticating users with either email or phone.
    """
    email_or_phone = serializers.CharField(write_only=True, required=True, help_text="User's email or phone for login")
    password = serializers.CharField(write_only=True, required=True, help_text="User's password")

    def validate(self, data):
        """
        Authenticates the user based on either email or phone and password, using targeted exception handling.

        Args:
            data (dict): Input data containing 'email_or_phone' and 'password'.

        Returns:
            dict: Validated data with the 'user' object.

        Raises:
            serializers.ValidationError:
                - If email or phone is not provided.
                - If user with the provided credentials doesn't exist.
                - If password is incorrect.
                - If the user account is not active (verified).
        """
        email_or_phone = data.get('email_or_phone')
        password = data.get('password')
        
        try:
            if '@' in email_or_phone:
                user = get_object_or_404(User, email=email_or_phone)
            else:
                user = get_object_or_404(User, phone=email_or_phone)
        except Exception as e:
            raise serializers.ValidationError({'email_or_phone': [_('User with this email or phone not found.')]})

        
        if not user.check_password(password):
            raise serializers.ValidationError({'password': [_('Incorrect password.')]})
        if not user.is_active:
            raise serializers.ValidationError({'non_field_errors': [_('Account not activated!!!. Check email/phone for OTP.')]})
       
        data['user'] = user
        return data








class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration, handling both email and phone registration.

    It validates the registration data and creates new user instances.
    """
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password], style={'input_type': 'password'}, help_text="User's password")
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'}, help_text="Confirm user's password")
    email = serializers.EmailField(required=False, allow_blank=True, help_text="User's email address")
    phone = PhoneNumberField(required=False, allow_blank=True, help_text="User's phone number")
    role = serializers.ChoiceField(choices=User.STATUS_CHOICES)                  # User's role (vendor or client)")

    class Meta:
        model = User
        fields = ('email', 'phone', 'role', 'password', 'password2')

    def validate(self, attrs):
        """
        Validates that email or phone is provided, passwords match, and email/phone is unique.

        Args:
            attrs (dict): Input data containing user registration information.

        Returns:
            dict: Validated data.

        Raises:
            serializers.ValidationError:
                - If passwords don't match.
                - If role is invalid.
                - If both email and phone are provided.
                - If neither email nor phone is provided.
                - If email is already in use.
                - If phone is already in use.
        """
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"Password": "Passwords do not match."})

        email = attrs.get('email')
        phone = attrs.get('phone')
        role = attrs.get('role')

        if role not in ['vendor', 'client']:
            raise serializers.ValidationError({'role': _("Invalid role value. Must be either 'vendor' or 'client'.")})

        if email and phone:
            raise serializers.ValidationError(
                {'non_field_errors': [_('Please Provide either An Email Address or A Phone Number, Not Both.')]}
            )

        if not email and not phone:
            raise serializers.ValidationError(
                {'non_field_errors': [_('Please Provide either An Email Address or A Phone Number, One Is Required.')]}
            )

        if email and User.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "A User with this Email Already Exists."})

        if phone and User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError({"phone": "A User with this Phone Number Already Exists."})

        return attrs

    def create(self, validated_data):
        """
        Creates a new user with either email or phone.

        Args:
            validated_data (dict): Validated user data.

        Returns:
            User: The newly created user instance.

        Raises:
            serializers.ValidationError: If an error occurs during user creation.
        """
        email = validated_data.get('email')
        phone = validated_data.get('phone')
        password = validated_data.get('password')
        role = validated_data.get('role')

        try:
            user = User.objects.create_user(
                email=email if email else None,
                phone=phone,
                password=password,
                role=role,
                is_active=False  # Ensure the account is not active immediately
            )
            return user
        except Exception as e:
            raise serializers.ValidationError({"error": f"An error occurred during user creation: {e}"})






class ResendOTPRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting OTP resend by email or phone.
    """
    email_or_phone = serializers.CharField(write_only=True, required=True, help_text="User's email or phone for RESEND OTP")

    def validate(self, data):
        """
        Validates that a user with the provided email or phone exists.

        Args:
            data (dict): Input data containing 'email_or_phone'.

        Returns:
            dict: Validated data.

        Raises:
            serializers.ValidationError: If the email or phone is invalid or user doesn't exist.
        """
        email_or_phone = data.get('email_or_phone')
        try:
            if '@' in email_or_phone:
                get_object_or_404(User, email=email_or_phone)
            else:
                get_object_or_404(User, phone=email_or_phone)
        except Exception as e:
            raise serializers.ValidationError({'email_or_phone': [_('User with this email or phone not found.')]})

        return data






class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting a password reset, accepting either email or phone.
    """
    email_or_phone = serializers.CharField(write_only=True, required=True, help_text="User's email or phone for password reset")

    def validate(self, data):
        """
        Validates that a user with the provided email or phone exists.

        Args:
            data (dict): Input data containing 'email_or_phone'.

        Returns:
            dict: Validated data.

        Raises:
            serializers.ValidationError: If the email or phone is invalid or user doesn't exist.
        """
        email_or_phone = data.get('email_or_phone')
        try:
            if '@' in email_or_phone:
                get_object_or_404(User, email=email_or_phone)
            else:
                get_object_or_404(User, phone=email_or_phone)
        except Exception as e:
            raise serializers.ValidationError({'email_or_phone': [_('User with this email or phone not found.')]})

        return data






class PasswordResetConfirmEmailSerializer(serializers.Serializer):
    """
    Serializer for confirming password reset.
    """
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password], help_text="New password")
    password2 = serializers.CharField(write_only=True, required=True, help_text="Confirm new password")

    def validate(self, attrs):
        """
        Validates that passwords match.

        Args:
            attrs (dict): Input data containing 'password' and 'password2'.

        Returns:
            dict: Validated data.

        Raises:
            serializers.ValidationError: If passwords don't match.
        """
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        
        return attrs






class PasswordResetConfirmPhoneSerializer(serializers.Serializer):
    """
    Serializer for confirming password reset.
    """
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password], help_text="New password")
    password2 = serializers.CharField(write_only=True, required=True, help_text="Confirm new password")
    otp = serializers.CharField(required=True, allow_blank=False, max_length=6, help_text="OTP sent to user's phone (if phone reset)")

    def validate(self, attrs):
        """
        Validates that passwords match.

        Args:
            attrs (dict): Input data containing 'password' and 'password2'.

        Returns:
            dict: Validated data.

        Raises:
            serializers.ValidationError: If passwords don't match.
        """
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        
        # Validate if OTP is 6 char
        otp = attrs.get('otp')
        if otp:
            if not (len(otp) == 6):
                raise serializers.ValidationError({"otp": "OTP length should be of six digits."})
        
        if not otp.isdigit():
            raise serializers.ValidationError({"otp": "OTP must contain only digits."})
            
        return attrs






class LogoutSerializer(serializers.Serializer):
    """
    Serializer for user logout.
    """
    refresh_token = serializers.CharField(help_text="Refresh token for logout")


class ProtectedUserSerializer(serializers.ModelSerializer):
    """
    Serializer to expose only safe user information.
    """
    class Meta:
        model = User
        fields = ('id', 'identifying_info',  'role', 'is_active','verified')  # No password!



from customer.serializers import DeliveryContactSerializer, ShippingAddressSerializer





class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the user profile.
    """
    user = ProtectedUserSerializer(read_only=True)

    class Meta:
        model = Profile
        fields = '__all__'

    def to_representation(self, instance):
        response = super().to_representation(instance)
        # Conditionally include related data only if they exist
        response['user'] = ProtectedUserSerializer(instance.user).data
        response['deliveryContact'] = DeliveryContactSerializer(instance.deliveryContact).data if instance.deliveryContact else None
        response['shippingAddress'] = ShippingAddressSerializer(instance.shippingAddress).data if instance.shippingAddress else None
        return response














