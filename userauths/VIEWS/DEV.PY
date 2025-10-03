from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django_redis import get_redis_connection
from userauths.models import User, Profile
from userauths.serializer import (
    OTPSerializer,
    LoginSerializer,
    UserRegistrationSerializer,
    ResendOTPRequestSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmEmailSerializer,
    PasswordResetConfirmPhoneSerializer,
    LogoutSerializer,
    ProfileSerializer,
    )
from django.db import transaction
from rest_framework import serializers as rest_serializers
from userauths.async_tasks import send_email_in_thread, send_sms_in_thread # UPDATED IMPORT
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q
import time
import random
from django.conf import settings
from cryptography.fernet import Fernet
import base64
import datetime


import logging
application_logger = logging.getLogger('application')

# Initialize Fernet cipher suite for OTP encryption/decryption
base_key = settings.SECRET_KEY.encode()
base_key = base_key.ljust(32, b'\0')[:32]  # Pad or truncate to ensure 32 bytes
cipher_suite = Fernet(base64.urlsafe_b64encode(base_key))

# Retry settings for Redis connection
REDIS_MAX_RETRIES = 3
REDIS_RETRY_DELAY = 1  # seconds






def encrypt_otp(otp):
    """
    Encrypts the given OTP using Fernet.
    """
    try:
        return cipher_suite.encrypt(otp.encode()).decode()
    except Exception as e:
        application_logger.error(f"OTP encryption failed: {e}")
        raise

def decrypt_otp(encrypted_otp):
    """
    Decrypts the given encrypted OTP using Fernet.
    """
    try:
        return cipher_suite.decrypt(encrypted_otp.encode()).decode()
    except Exception as e:
        application_logger.error(f"OTP decryption failed: {e}")
        raise


def get_redis_connection_safe(max_retries=REDIS_MAX_RETRIES, retry_delay=REDIS_RETRY_DELAY):
    """
    Establishes a safe connection to Redis, logging errors and returning None if unavailable.
    Implements retry mechanism for transient Redis failures.
    """
    for attempt in range(max_retries):
        try:
            redis_conn = get_redis_connection("default")
            redis_conn.ping()  # Ensure Redis is available
            return redis_conn
        except Exception as e:
            application_logger.error(f"Redis connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)  # Wait before retrying
            else:
                application_logger.error("Max Redis connection retries reached. Redis unavailable.")
                return None
    return None


def generate_numeric_otp(length=6):
    """
    Generates a numeric OTP of the specified length.
    """
    return ''.join(random.choices('0123456789', k=length))


def get_otp_expiry_datetime():
    """
    Calculates the OTP expiry datetime.

    Returns:
        datetime: A datetime object representing the OTP expiry time.
    """
    timestamp = time.time() + 300
    dt_object = datetime.datetime.fromtimestamp(timestamp)
    dt_object += datetime.timedelta()
    return dt_object











class RegisterViewThread(generics.CreateAPIView): # Renamed for clarity
    """
    Registers a new user, sending an OTP via email or SMS, and stores the encrypted token in Redis.

    This endpoint handles user registration by accepting either an email or a phone number,
    validating the input, creating a user account, and sending a One-Time Password (OTP)
    for account verification. The OTP is delivered via email or SMS depending on the
    user's provided contact information.

    The OTP is encrypted before being stored in Redis with an expiry time of 300 seconds.
    The user ID is also stored in Redis to associate the OTP with the user.
    The key structure in Redis includes the user ID to prevent OTP collisions.

    The endpoint uses atomic transactions to ensure data consistency; if any part of the
    registration process fails, the entire transaction is rolled back, preventing partial
    user creation. It also retries Redis connections and logs if OTP encryption fails.

    Serializer errors are formatted into a user-friendly JSON response, aiding debugging.
    """
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = UserRegistrationSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Creates a new user and sends an OTP via email or SMS.
        """
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            user = serializer.save()
            user_id = user.id  # Get user ID

            application_logger.info(f"User {user.identifying_info} registered successfully.")

            # Generate OTP
            otp = generate_numeric_otp()
            application_logger.info(f"Generated OTP: {otp} for user {user.identifying_info}")

            # Encrypt OTP before storing in Redis
            try:
                encrypted_otp = encrypt_otp(otp)
                application_logger.info(f"Encrypted OTP: {encrypted_otp} for user {user.identifying_info}")
            except Exception as e:
                transaction.set_rollback(True)
                return Response({'error': 'Failed to encrypt OTP.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


            # Check Redis Connection
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                transaction.set_rollback(True)  # Rollback
                return Response({'error': 'Redis Server Service Temporary unavailable Now, Please Try Again later.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            # Store OTP data in Redis with expiry, using user_id in the key to prevent collisions
            otp_expiry_datetime = get_otp_expiry_datetime()
            otp_data = {'user_id': user.id, 'otp': encrypted_otp}  # Store encrypted OTP
            redis_key = f"otp_data:{user_id}:{encrypted_otp}" # Use the User ID in the Redis Key
            redis_conn.setex(redis_key, 300, str(otp_data))  # Use hardcoded 300 seconds for expiry


            # Determine whether to send via email or SMS
            if user.email:
                subject = 'Verify Your Email'
                template_name = 'otp.html'
                context = {'user': user.id, 'token': otp, 'time': otp_expiry_datetime}

                # Use Thread for Sending Email (replaces Celery task)
                send_email_in_thread(subject, [user.email], template_name, context)

                application_logger.info(f"Sent OTP email to {user.email} using Threading.")
                message = "Registration successful. Please check your email for OTP verification."

            elif user.phone:
                body = f"Your OTP is: {otp}"
                send_sms_in_thread(user.phone.as_e164, body)  # Pass user_id to the SMS task
                application_logger.info(f"Sent OTP SMS to {user.phone} using Threading.")
                message = "Registration successful. Please check your phone for OTP verification."
            else:
                application_logger.error(f"User {user.identifying_info} has neither email nor phone.")
                return Response({'error': 'User has neither email nor phone.'}, status=status.HTTP_400_BAD_REQUEST)

            return Response({'message': message}, status=status.HTTP_201_CREATED)

        except rest_serializers.ValidationError as e:  # Catch serializer validation errors specifically
            application_logger.warning(f"Invalid registration attempt: {e}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)  # Return Serializer Errors

        except Exception as e:
            application_logger.error(f"An unexpected error occurred: {e} during registration. Error: {str(e)}")
            transaction.set_rollback(True)  # Rollback
            return Response({'error': f"An error occurred, please check your input or contact support. {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)








class VerifyOTPView(generics.GenericAPIView):
    """
    Verifies the OTP entered by the user.

    This endpoint receives the OTP, retrieves the user ID from Redis
    based on the OTP, decrypts it, compares it with the provided OTP, and if valid,
    activates the user account. It clears the OTP from Redis after
    successful verification.

    If the OTP has expired, it returns an error message.
    The key structure in Redis includes the user ID to prevent OTP collisions.
    """
    permission_classes = (AllowAny,)
    serializer_class = OTPSerializer

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """
        Verifies the OTP and activates the user account.
        """
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            otp = serializer.validated_data['otp']

            # Check Redis Connection
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                transaction.set_rollback(True)  # Rollback
                return Response({'error': 'Redis Server Service Temporary unavailable Now, Please Try Again later.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            # Search for the OTP using scan_iter since the user_id is needed to find the key
            user_id = None
            redis_key = None
            for key in redis_conn.scan_iter(match="otp_data:*"): #Find the key
                otp_data_str = redis_conn.get(key)
                if otp_data_str:
                     otp_data = eval(otp_data_str.decode('utf-8'))
                     decrypted_otp = decrypt_otp(otp_data.get('otp')) #decrypt the otp

                     if decrypted_otp == otp:   #If decrypted OTP is correct
                         user_id = otp_data.get('user_id')   # get user_id
                         redis_key = key #Get Redis Key
                         break #break loop
                else:
                   application_logger.warning(f"Invalid or expired OTP: {otp}")
                   return Response({'error': 'Invalid or expired OTP. Please request a new one if it has expired.'}, status=status.HTTP_400_BAD_REQUEST)

            if not user_id:
                application_logger.warning(f"Invalid or expired OTP: {otp}")
                return Response({'error': 'Invalid or expired OTP. Please request a new one if it has expired.'}, status=status.HTTP_400_BAD_REQUEST)

            # Ensure user_id is valid before querying the database
            try:
                # Fetch user in a single optimized query
                user = get_object_or_404(User.objects.only("id", "is_active", "verified"), id=user_id)  # Fetch user *after* OTP is validated
            except Exception as e:
                application_logger.error(f"User not found with ID {user_id}: {e}")
                return Response({'error': 'Invalid OTP. Please request a new one if it has expired.'}, status=status.HTTP_400_BAD_REQUEST)


            # Update user verification status
            if not user.is_active:
                user.is_active = True
            user.verified = True
            user.save()
            application_logger.info(f"User {user.id} successfully verified.")

            # Delete OTP data from Redis after successful verification
            redis_conn.delete(redis_key) # Delete the Redis Key

            ####  LOGIN THE USER DIRECTLY IMMEDIATELY AFTER OTP VERIFICATION

            # Generate JWT token
            refresh = RefreshToken.for_user(user)

            application_logger.info(f"User {user.identifying_info} logged in successfully.")
            return Response({
                'message': "Your account has been successfully verified.",
                'user_id': user.id,
                'role': user.role,
                'identifying_info': user.identifying_info,  # Either the PhoneNumber or Email
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_200_OK)

        except rest_serializers.ValidationError as e:  # Catch serializer validation errors specifically
            application_logger.warning(f"Invalid OTP Verification attempt: {e}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)  # Return Serializer Errors

        except Exception as e:
            application_logger.exception(f"Error during OTP verification: {e}")
            transaction.set_rollback(True)
            return Response({'error': 'An error occurred during verification. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class ResendOTPView(generics.GenericAPIView):
    """
    Resends the OTP to the user's email or phone if the previous OTP has expired.
    """
    permission_classes = (AllowAny,)
    serializer_class = ResendOTPRequestSerializer

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """
        Resends the OTP based on email or phone number.
        """
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            email_or_phone = serializer.validated_data['email_or_phone']

            # Check Redis Connection
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                transaction.set_rollback(True)  # Rollback
                return Response({'error': 'Redis Server Service Temporary unavailable Now, Please Try Again later.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            # Retrieve user based on email or phone
            try:
                user = get_object_or_404(User, email=email_or_phone) if '@' in email_or_phone else get_object_or_404(User, phone=email_or_phone)
            except Exception as e:
                application_logger.error(f"User not found with ID {email_or_phone}: {e}")
                return Response({'error': 'User with this credentials not found'}, status=status.HTTP_400_BAD_REQUEST)

            # Delete the old OTP data using scan_iter since User id is required to find the key
            otp_exists = False
            for key in redis_conn.scan_iter(match="otp_data:*"): #Find the key
                otp_data_str = redis_conn.get(key)
                if otp_data_str:
                    otp_data = eval(otp_data_str.decode('utf-8'))
                    if otp_data.get('user_id') == user.id:   #If User Id is equal
                        otp_exists = True
                        redis_conn.delete(key) #Delete Key
                        break #Break Loop
                else:
                   application_logger.warning(f"Invalid or expired OTP for user {user.id}")
                   return Response({'error': 'Invalid or expired OTP. Please request a new one if it has expired.'}, status=status.HTTP_400_BAD_REQUEST)

            # Generate a new OTP
            otp = generate_numeric_otp()
            application_logger.info(f"Generated new OTP: {otp} for user {user.id}")

            # Encrypt OTP before storing in Redis
            try:
                encrypted_otp = encrypt_otp(otp)
                application_logger.info(f"Encrypted OTP: {encrypted_otp} for user {user.identifying_info}")
            except Exception as e:
                transaction.set_rollback(True)
                return Response({'error': 'Failed to encrypt OTP.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Store new OTP data in Redis, using user_id in the key to prevent collisions
            otp_expiry_datetime = get_otp_expiry_datetime()
            otp_data = {'user_id': user.id, 'otp': encrypted_otp}  # Store encrypted OTP
            redis_key = f"otp_data:{user.id}:{encrypted_otp}" # Use the User ID in the Redis Key
            redis_conn.setex(redis_key, 300, str(otp_data))



            # Send the OTP via email or SMS
            if user.email:
                subject = 'Your New OTP'
                template_name = 'otp.html'
                context = {'user': user.id, 'token': otp, 'time': otp_expiry_datetime}

                # Use Thread for Sending Email (replaces Celery task)
                send_email_in_thread(subject, [user.email], template_name, context)

                application_logger.info(f"Resent OTP email to {user.email} using Threading.")
                message = "New OTP sent to your email."

            elif user.phone:
                body = f"Your new OTP is: {otp}"
                send_sms_in_thread(user.phone.as_e164, body)
                application_logger.info(f"Resent OTP SMS to {user.phone} using Threading.")
                message = "New OTP sent to your phone."
            else:
                application_logger.error(f"User {user.id} has neither email nor phone.")
                return Response({'error': 'User has neither email nor phone.'}, status=status.HTTP_400_BAD_REQUEST)

            # Customize response message based on whether OTP existed before resending
            response_message = "New OTP sent successfully." if otp_exists else "OTP has been resent successfully."

            return Response({'message': response_message}, status=status.HTTP_200_OK)

        except rest_serializers.ValidationError as e:
            application_logger.warning(f"Invalid Resend OTP attempt: {e}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            application_logger.exception(f"Error during OTP resend: {e}")
            transaction.set_rollback(True)
            return Response({'error': 'An error occurred while resending the OTP. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class LoginView(generics.GenericAPIView):
    """
    Logs in an existing user with either email or phone, using targeted exception handling.
    """
    permission_classes = (AllowAny,)
    serializer_class = LoginSerializer

    def post(self, request):
        """
        Logs in an existing user with either email or phone, using targeted exception handling.
        """
        try:
            serializer = self.get_serializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)  # Check if Serializer has validation Errors

            user = serializer.validated_data['user']  # Get User Instance
            print(user.identifying_info)  # Email or Phone

            # Generate JWT token
            refresh = RefreshToken.for_user(user)

            application_logger.info(f"User {user.identifying_info} logged in successfully.")
            return Response({
                'message': "Login successful.",
                'user_id': user.id,
                'role': user.role,
                'identifying_info': user.identifying_info,  # Either the PhoneNumber or Email
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_200_OK)

        except rest_serializers.ValidationError as e:  # Catch serializer validation errors specifically
            application_logger.warning(f"Invalid login attempt: {e}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)  # Return Serializer Errors

        except Exception as e:  # Catch other exceptions
            application_logger.error(f"An unexpected error occurred: {e} during login.")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class PasswordResetRequestView(generics.GenericAPIView):
    """
    Requests a password reset by sending a unique link to the user's email OR SMS OTP to phone.
    """
    permission_classes = (AllowAny,)
    serializer_class = PasswordResetRequestSerializer

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """
        Sends a password reset link to the user's email or an SMS OTP to the phone.
        """
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            email_or_phone = serializer.validated_data['email_or_phone']

            # Check Redis Connection
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                transaction.set_rollback(True)  # Rollback
                return Response({'error': 'Redis Server Service Temporary unavailable Now, Please Try Again later.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            # Retrieve user based on email or phone
            try:
                user = get_object_or_404(User, Q(email=email_or_phone) | Q(phone=email_or_phone))

                # EMAIL FLOW
                if user.email:
                    # Check and Delete Existing RESET Email Data
                    for key in redis_conn.scan_iter(f"reset_email_data:*"):
                        reset_email_data_str = redis_conn.get(key)
                        if reset_email_data_str:
                            reset_email_data = eval(reset_email_data_str.decode('utf-8'))
                            if reset_email_data.get('user_id') == user.id:
                                redis_conn.delete(key)
                                break

                    # Generate a unique token for email
                    token = default_token_generator.make_token(user)
                    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                    application_logger.info(f"Generated password reset token for user {user.identifying_info}")

                    # Store all email data in a single Redis key with expiry
                    reset_email_data = {'user_id': user.id, 'uidb64': uidb64, 'token': token}
                    reset_email_key = f"reset_email_data:{user.id}:{uidb64}:{token}"  # Include user ID
                    redis_conn.setex(reset_email_key, 300, str(reset_email_data))

                    # Build password reset link
                    current_site = get_current_site(request)
                    reset_url = reverse('password-reset-confirm-email', kwargs={'uidb64': uidb64, 'token': token})
                    absurl = f"http://{current_site.domain}{reset_url}"

                    # Send password reset email using Thread (replaces Celery task)
                    subject = 'Password Reset Request'
                    template_name = 'password_reset.html'
                    context = {'reset_url': absurl, 'user': user.identifying_info}
                    send_email_in_thread(subject, [user.email], template_name, context)

                    application_logger.info(f"Sent password reset link email to {user.email} using Threading.")
                    return Response({'message': 'Password reset link sent to your email.'}, status=status.HTTP_200_OK)

                # PHONE FLOW
                elif user.phone:
                    # Check and Delete Existing OTP Data
                    for key in redis_conn.scan_iter(f"reset_otp_data:*"):
                        otp_data_str = redis_conn.get(key)
                        if otp_data_str:
                            otp_data = eval(otp_data_str.decode('utf-8'))
                            if otp_data.get('user_id') == user.id:
                                redis_conn.delete(key)
                                break

                    # Generate OTP
                    otp = generate_numeric_otp()
                    application_logger.info(f"Generated OTP: {otp} for user {user.identifying_info}")

                     # Encrypt OTP before storing in Redis
                    try:
                        encrypted_otp = encrypt_otp(otp)
                        application_logger.info(f"Encrypted OTP: {encrypted_otp} for user {user.identifying_info}")
                    except Exception as e:
                        transaction.set_rollback(True)
                        return Response({'error': 'Failed to encrypt OTP.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                    # Store all OTP data in a single Redis key with expiry
                    otp_data = {'user_id': user.id, 'otp':