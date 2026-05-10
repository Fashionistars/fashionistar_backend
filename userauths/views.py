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
from userauths.tasks import send_email_task, send_sms_task
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q
from celery import signature

from utilities.django_redis import ( 
    encrypt_otp, 
    decrypt_otp, 
    get_redis_connection_safe,
    generate_numeric_otp, 
    get_otp_expiry_datetime 
)



import logging
application_logger = logging.getLogger('application')




class RegisterViewCelery(generics.CreateAPIView):
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

                # Use Celery Signature for Sending and Tracking Email Task
                email_task = signature('userauths.tasks.send_email_task', args=(subject, [user.email], template_name, context))
                email_task.apply_async()

                application_logger.info(f"Sent OTP email to {user.email} using Celery.")
                message = "Registration successful. Please check your email for OTP verification."

            elif user.phone:
                body = f"Your OTP is: {otp}"
                send_sms_task.delay(user.phone.as_e164, body)  # Pass user_id to the SMS task
                application_logger.info(f"Sent OTP SMS to {user.phone} using Celery.")
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

                # Use Celery Signature for Sending and Tracking Email Task
                email_task = signature('userauths.tasks.send_email_task', args=(subject, [user.email], template_name, context))
                email_task.apply_async()

                application_logger.info(f"Resent OTP email to {user.email} using Celery.")
                message = "New OTP sent to your email."

            elif user.phone:
                body = f"Your new OTP is: {otp}"
                send_sms_task.delay(user.phone.as_e164, body)
                application_logger.info(f"Resent OTP SMS to {user.phone} using Celery.")
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

                    # Send password reset email
                    subject = 'Password Reset Request'
                    template_name = 'password_reset.html'
                    context = {'reset_url': absurl, 'user': user.identifying_info}

                    # Use Celery Signature for Sending and Tracking Email Task
                    email_task = signature('userauths.tasks.send_email_task', args=(subject, [user.email], template_name, context))
                    email_task.apply_async()

                    application_logger.info(f"Sent password reset link email to {user.email} using Celery.")
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
                    otp_data = {'user_id': user.id, 'otp': encrypted_otp}  # Store encrypted OTP
                    redis_key = f"reset_otp_data:{user.id}:{encrypted_otp}"  # Include user ID
                    redis_conn.setex(redis_key, 300, str(otp_data))

                    current_site = get_current_site(request)
                    reset_url = reverse('password-reset-confirm-phone')
                    absurl = f"http://{current_site.domain}{reset_url}"

                    # Send password reset SMS
                    body = f"Your password reset OTP is: {otp}"
                    send_sms_task.delay(user.phone.as_e164, body)  # Use Celery for sending SMS

                    application_logger.info(f"Sent password reset OTP SMS to {user.phone} using Celery.")
                    return Response({'message': f'Password reset OTP sent to your phone. Kindly proceed to visit {absurl} to make a reset with your phone OTP and new password.'}, status=status.HTTP_200_OK)

                else:
                    application_logger.error(f"User {user.identifying_info} has neither email nor phone.")
                    return Response({'error': 'User has neither email nor phone configured.'}, status=status.HTTP_400_BAD_REQUEST)

            except User.DoesNotExist:
                application_logger.warning(f"User with email or phone {email_or_phone} not found.")
                return Response({'error': 'Invalid email or phone.'}, status=status.HTTP_404_NOT_FOUND)

        except rest_serializers.ValidationError as e:  # Catch serializer validation errors specifically
            application_logger.warning(f"Invalid Password Reset Request attempt: {e}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)  # Return Serializer Errors

        except Exception as e:
            application_logger.exception(f"Error during password reset request: {e}")
            transaction.set_rollback(True)
            return Response({'error': 'An error occurred while processing the password reset request.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class PasswordResetConfirmEmailView(generics.GenericAPIView):
    """
    Confirms the password reset by verifying the token and setting the new password.
    """
    permission_classes = (AllowAny,)
    serializer_class = PasswordResetConfirmEmailSerializer

    @transaction.atomic
    def post(self, request, uidb64, token, *args, **kwargs):
        """
        Verifies the token and sets the new password using Email flow
        """
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            password = serializer.validated_data['password']

            # Check Redis Connection
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                transaction.set_rollback(True)  # Rollback
                return Response({'error': 'Redis Server Service Temporary unavailable Now, Please Try Again later.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            # Optimized Redis retrieval using scan_iter since it requires User ID
            user_id = None
            reset_email_key = None

            for key in redis_conn.scan_iter(match="reset_email_data:*"): #Find the key
                reset_email_data_str = redis_conn.get(key)
                if reset_email_data_str:
                    reset_email_data = eval(reset_email_data_str.decode('utf-8'))
                    if reset_email_data.get('uidb64') == uidb64 and reset_email_data.get('token') == token:   #If uidb64 and token is equal
                        user_id = reset_email_data.get('user_id')   # get user_id
                        reset_email_key = key #Get Redis Key
                        break #break loop
                else:
                   application_logger.warning(f"Invalid or expired Data for reset Email for user {user_id}")
                   return Response({'error': 'Invalid or expired Data for reset Email.'}, status=status.HTTP_400_BAD_REQUEST)

            if not user_id:
                application_logger.warning(f"Invalid or expired reset link for user")
                return Response({'error': 'Invalid or expired reset link.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                uid = force_str(urlsafe_base64_decode(uidb64))
                user = get_object_or_404(User.objects.only("id"), pk=uid)

            except Exception as e:
                application_logger.warning(f"Invalid user ID in password reset confirmation: {uidb64}, error: {e}")
                return Response({'error': 'Invalid reset link.'}, status=status.HTTP_400_BAD_REQUEST)

            # Verify the token
            if not default_token_generator.check_token(user, token):
                application_logger.warning(f"Invalid token in password reset confirmation for user {user.id}.")
                return Response({'error': 'Invalid reset link.'}, status=status.HTTP_400_BAD_REQUEST)

            # Set the new password
            user.set_password(password)
            user.save()
            application_logger.info(f"Password reset successfully for user {user.id}.")

            # Delete the token from Redis
            redis_conn.delete(reset_email_key)

            return Response({'message': 'Password reset successfully.'}, status=status.HTTP_200_OK)

        except rest_serializers.ValidationError as e:
            application_logger.warning(f"Invalid Password Reset Confirm attempt: {e}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            application_logger.exception(f"Error during password reset confirmation: {e}")
            transaction.set_rollback(True)
            return Response({'error': 'An error occurred during password reset confirmation. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class PasswordResetConfirmPhoneView(generics.GenericAPIView):
    """
    Confirms the password reset PHONE by verifying the OTP and setting the new password.
    """
    permission_classes = (AllowAny,)
    serializer_class = PasswordResetConfirmPhoneSerializer

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """
        Verifies the OTP and sets the new password for PHONE.
        """
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            password = serializer.validated_data['password']
            otp = serializer.validated_data['otp']  # Get OTP from serializer

            # Check Redis Connection
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                transaction.set_rollback(True)  # Rollback
                return Response({'error': 'Redis Server Service Temporary unavailable Now, Please Try Again later.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            # Optimized Redis retrieval using scan_iter since it requires User ID
            user_id = None
            redis_key = None

            for key in redis_conn.scan_iter(match="reset_otp_data:*"): #Find the key
                otp_data_str = redis_conn.get(key)
                if otp_data_str:
                     otp_data = eval(otp_data_str.decode('utf-8'))
                     decrypted_otp = decrypt_otp(otp_data.get('otp'))  #decrypt the otp
                     if  decrypted_otp == otp:   #If OTP is equal
                         user_id = otp_data.get('user_id')   # get user_id
                         redis_key = key #Get Redis Key
                         break #break loop
                else:
                   application_logger.warning(f"Invalid or expired Data for reset OTP for user {user_id}")
                   return Response({'error': 'Invalid or expired Data for reset OTP.'}, status=status.HTTP_400_BAD_REQUEST)

            if not user_id:
                application_logger.warning(f"Invalid or expired OTP: {otp}")
                return Response({'error': 'Invalid or expired OTP. Please request a new one if it has expired.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                # Fetch user in a single optimized query
                user = get_object_or_404(User.objects.only("id"), id=user_id)  # Fetch user *after* OTP is validated
            except Exception as e:
                application_logger.error(f"User not found with ID {user_id}: {e}")
                return Response({'error': 'Invalid OTP. Please request a new one if it has expired.'}, status=status.HTTP_400_BAD_REQUEST)

            # Set new password
            user.set_password(password)
            user.save()
            application_logger.info(f"Password reset successfully for user {user.identifying_info}.")

            # Clear OTP from Redis after successful verification
            redis_conn.delete(redis_key)

            return Response({'message': 'Password reset successfully.'}, status=status.HTTP_200_OK)

        except rest_serializers.ValidationError as e:  # Catch serializer validation errors specifically
            application_logger.warning(f"Invalid Password Reset Confirm attempt: {e}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)  # Return Serializer Errors

        except Exception as e:
            application_logger.exception(f"Error during password reset confirmation: {e}")
            transaction.set_rollback(True)
            return Response({'error': 'An error occurred during password reset confirmation.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class LogoutView(generics.GenericAPIView):
    """
    Logs out a user by blacklisting the refresh token.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = LogoutSerializer

    def post(self, request, *args, **kwargs):
        """
        Blacklists the refresh token to log the user out.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            refresh_token = serializer.validated_data['refresh_token']
            token = RefreshToken(refresh_token)
            token.blacklist()
            application_logger.info(f"User {request.user.username} logged out.")
            return Response({'message': 'Successfully logged out.'}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            application_logger.exception(f"Logout error: {e}")
            return Response({'error': 'An error occurred during logout.'}, status=status.HTTP_400_BAD_REQUEST)







class ProfileView(generics.RetrieveUpdateAPIView):
    """
    Retrieves or updates the user's profile.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = ProfileSerializer

    def get_object(self):
        """
        Returns the user's profile.
        """
        return self.request.user.profile  # Efficiently fetch profile

        # return get_object_or_404(Profile, user=self.request.user)  # Efficiently fetch profile

    def update(self, request, *args, **kwargs):
        """
        Handles profile updates.
        """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)  # Allow partial updates
            serializer.is_valid(raise_exception=True)
            serializer.save()
            application_logger.info(f"Profile updated for user: {request.user.username}")
            return Response(serializer.data)
        except Exception as e:
            application_logger.exception(f"Profile update error: {e}")
            return Response({'error': 'An error occurred during profile update.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class USERSPROFILELISTVIEW(generics.ListAPIView):
    """
    Lists all user profiles.
    """
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = (AllowAny,) # Update Permission Classes

    def get_queryset(self):
        """
        Retrieves all user profiles.
        """
        try:
            return super().get_queryset()
        except Exception as e:
            print(f"Error retrieving ALL USERS: {e}")
            return Profile.objects.none()






















