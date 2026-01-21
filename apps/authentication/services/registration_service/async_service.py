# apps/authentication/services/registration_service/async_service.py

import logging
import asyncio
from celery import signature
from asgiref.sync import sync_to_async
from apps.authentication.models import UnifiedUser
from apps.authentication.tasks import send_sms_task
from utilities.django_redis import get_redis_connection_safe, encrypt_otp, generate_numeric_otp, get_otp_expiry_datetime

logger = logging.getLogger('application')

class AsyncRegistrationService:
    """
    Asynchronous Service for User Registration.
    Uses native async ORM where possible, offloads blocking crypto/redis/celery to threads.
    """

    @staticmethod
    async def register_user(validated_data):
        """
        Async version of register_user.
        """
        try:
            # 1. Create User (Native Async)
            # Handle atomic transaction: strict async transaction support in Django < 5.x is tricky.
            # Django 6.0 supports it better, but often easiest to wrap the whole atomic block if needed.
            # However, create_user is sync. We should use acreate_user if available (Django 5+) or wrap.
            # UnifiedUser manager likely doesn't have acreate_user custom method yet unless standard.
            # Standard Django Client `objects.acreate` works for models.
            # Let's clean data first.
            
            extra_fields = {k: v for k, v in validated_data.items() if k not in ['email', 'phone', 'password', 'role', 'password2']}
            email = validated_data.get('email')
            phone = validated_data.get('phone')
            password = validated_data['password']
            role = validated_data.get('role', 'client')

            # We need to use Manager's create_user to handle password hashing signal etc.
            # Manager.create_user is generally Sync.
            # Best practice: Wrapper for atomic + create_user
            def _create_user_atomic():
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
            otp = generate_numeric_otp()
            
            def _encrypt():
                return encrypt_otp(otp)
            
            encrypted_otp = await asyncio.to_thread(_encrypt)

            # 3. Store in Redis (IO Bound -> Thread)
            def _store_redis():
                conn = get_redis_connection_safe()
                if not conn:
                    raise Exception("Redis Unavailable")
                
                # Optimized Key: otp_data:{user_id}
                key = f"otp_data:{user.id}"
                data = {'user_id': user.id, 'otp': encrypted_otp}
                conn.setex(key, 300, str(data))
                
            await asyncio.to_thread(_store_redis)

            # 4. Dispatch Notifications (Celery -> Thread)
            message = ""
            if user.email:
                subject = 'Verify Your Email'
                template_name = 'otp.html'
                # Pre-calculate context needs serializable data
                # get_otp_expiry_datetime returns datetime, safe? usually yes for celery json with encoder
                # But safer to cast to str if custom encoder not set. Celery default handles ISO format?
                # Let's rely on DjangoJSONEncoder if configured, else str() it.
                context = {'user': user.id, 'token': otp, 'time': str(get_otp_expiry_datetime())}
                
                def _dispatch_email():
                    sig = signature('apps.authentication.tasks.send_email_task', args=(subject, [user.email], template_name, context))
                    sig.apply_async()
                
                await asyncio.to_thread(_dispatch_email)
                message = "Registration successful. Please check your email for OTP verification."

            elif user.phone:
                body = f"Your OTP is: {otp}"
                # send_sms_task.delay is trigger, wraps apply_async
                await asyncio.to_thread(send_sms_task.delay, user.phone.as_e164, body)
                message = "Registration successful. Please check your phone for OTP verification."

            return user, message

        except Exception as e:
            logger.error(f"Async Registration Error: {e}")
            raise e
