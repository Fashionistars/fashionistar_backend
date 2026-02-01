# apps/authentication/services/registration_service/sync_service.py

import logging
from typing import Dict, Tuple, Any
from django.db import transaction
from celery import signature
from apps.authentication.models import UnifiedUser
from apps.authentication.tasks import send_sms_task
from apps.common.utils import (
    get_redis_connection_safe, 
    encrypt_otp, 
    generate_numeric_otp, 
    get_otp_expiry_datetime
)

logger = logging.getLogger('application')

class SyncRegistrationService:
    """
    Synchronous Service for User Registration.
    Strictly follows legacy logic with industrial-grade enhancements and type hints.
    """

    @staticmethod
    def register_user(validated_data: Dict[str, Any]) -> Tuple[UnifiedUser, str]:
        """
        Registers a verified user, generates OTP, stores in Redis, and dispatches via Celery.
        
        Args:
            validated_data (dict): Cleaned data from serializer.
            
        Returns:
            Tuple(User, str): Created user instance and success message.
            
        Raises:
            Exception: On DB, Redis, or Logic failure.
        """
        try:
            with transaction.atomic():
                # 1. Create User
                # Extract extra fields
                extra_fields = {k: v for k, v in validated_data.items() if k not in ['email', 'phone', 'password', 'role', 'password2']}
                
                email: str = validated_data.get('email')
                phone: Any = validated_data.get('phone') # PhoneNumber object
                password: str = validated_data['password']
                role: str = validated_data.get('role', 'client')

                # Create user
                user = UnifiedUser.objects.create_user(
                    email=email,
                    phone=phone,
                    password=password,
                    role=role,
                    is_active=False,
                    is_verified=False,
                    **extra_fields
                )
                
                logger.info(f"User {user.identifying_info} registered successfully within atomic transaction.")

                # 2. Generate OTP
                otp: str = generate_numeric_otp()
                logger.info(f"Generated OTP for user {user.identifying_info}")

                # 3. Encrypt OTP
                try:
                    encrypted_otp: str = encrypt_otp(otp)
                except Exception as e:
                    logger.error(f"OTP Encryption Failed: {e}")
                    raise Exception("Failed to encrypt OTP.")

                # 4. Store in Redis
                redis_conn = get_redis_connection_safe()
                if not redis_conn:
                    logger.error("Redis Connection Failed during Registration.")
                    raise Exception("Service Temporarily Unavailable (Redis).")

                # Key: otp_data:{user_id} -> O(1) Lookup
                otp_data = {'user_id': user.id, 'otp': encrypted_otp}
                redis_key = f"otp_data:{user.id}" 
                redis_conn.setex(redis_key, 300, str(otp_data))

                # 5. Dispatch Notification (Async via Celery)
                message: str = ""
                if user.email:
                    subject = 'Verify Your Email'
                    template_name = 'otp.html'
                    # Cast datetime to str for serialization safety
                    context = {'user': user.id, 'token': otp, 'time': str(get_otp_expiry_datetime())}
                    
                    email_task = signature('apps.authentication.tasks.send_email_task', args=(subject, [user.email], template_name, context))
                    email_task.apply_async()
                    
                    logger.info(f"Sent OTP email task to {user.email}")
                    message = "Registration successful. Please check your email for OTP verification."

                elif user.phone:
                    body = f"Your OTP is: {otp}"
                    send_sms_task.delay(user.phone.as_e164, body)
                    logger.info(f"Sent OTP SMS task to {user.phone}")
                    message = "Registration successful. Please check your phone for OTP verification."
                
                return user, message

        except Exception as e:
            logger.error(f"Registration Service Error: {e}")
            raise e
