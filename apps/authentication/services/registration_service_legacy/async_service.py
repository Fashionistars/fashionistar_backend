# apps/authentication/services/registration_service/async_service.py

import logging
import asyncio
from typing import Dict, Tuple, Any
from celery import signature
from asgiref.sync import sync_to_async
from apps.authentication.models import UnifiedUser
from apps.authentication.tasks import send_sms_task
from apps.common.utils import (
    get_redis_connection_safe, 
    encrypt_otp, 
    generate_numeric_otp, 
    get_otp_expiry_datetime
)

logger = logging.getLogger('application')

class AsyncRegistrationService:
    """
    Asynchronous Service for User Registration.
    Uses native async ORM where possible, offloads blocking crypto/redis/celery to threads.
    Strict type hinting applied.
    """

    @staticmethod
    async def register_user(validated_data: Dict[str, Any]) -> Tuple[UnifiedUser, str]:
        """
        Async version of register_user.
        
        Args:
            validated_data (dict): Cleaned data from serializer.
            
        Returns:
            Tuple(User, str): Created user instance and success message.
        """
        try:
            extra_fields = {k: v for k, v in validated_data.items() if k not in ['email', 'phone', 'password', 'role', 'password2']}
            email: str = validated_data.get('email')
            phone: Any = validated_data.get('phone')
            password: str = validated_data['password']
            role: str = validated_data.get('role', 'client')

            # 1. Create User (Atomic wrapper offload)
            def _create_user_atomic() -> UnifiedUser:
                user = UnifiedUser.objects.create_user(
                    email=email,
                    phone=phone,
                    password=password,
                    role=role,
                    is_active=False,
                    is_verified=False,
                    **extra_fields
                )
                return user
            
            user = await asyncio.to_thread(_create_user_atomic)
            logger.info(f"User {user.identifying_info} registered (Async).")

            # 2. Generate & Encrypt OTP (Cpu Bound -> Thread)
            otp: str = generate_numeric_otp()
            
            def _encrypt() -> str:
                return encrypt_otp(otp)
            
            encrypted_otp: str = await asyncio.to_thread(_encrypt)

            # 3. Store in Redis (IO Bound -> Thread)
            def _store_redis():
                conn = get_redis_connection_safe()
                if not conn:
                    raise Exception("Redis Unavailable")
                
                key = f"otp_data:{user.id}"
                data = {'user_id': user.id, 'otp': encrypted_otp}
                conn.setex(key, 300, str(data))
                
            await asyncio.to_thread(_store_redis)

            # 4. Dispatch Notifications (Celery -> Thread)
            message: str = ""
            if user.email:
                subject = 'Verify Your Email'
                template_name = 'otp.html'
                
                # Pre-calculate context
                def _get_context() -> dict:
                    return {'user': user.id, 'token': otp, 'time': str(get_otp_expiry_datetime())}
                
                context = await asyncio.to_thread(_get_context)
                
                def _dispatch_email():
                    sig = signature('apps.authentication.tasks.send_email_task', args=(subject, [user.email], template_name, context))
                    sig.apply_async()
                
                await asyncio.to_thread(_dispatch_email)
                message = "Registration successful. Please check your email for OTP verification."

            elif user.phone:
                body = f"Your OTP is: {otp}"
                await asyncio.to_thread(send_sms_task.delay, user.phone.as_e164, body)
                message = "Registration successful. Please check your phone for OTP verification."

            return user, message

        except Exception as e:
            logger.error(f"Async Registration Error: {e}")
            raise e
