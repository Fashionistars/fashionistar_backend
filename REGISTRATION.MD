# 📋 REGISTRATION ENDPOINT — 5-Step Implementation Plan

> **Scope**: ONLY Registration (Register → Verify OTP → Resend OTP).  
> **Login, Password Reset, Logout** are deferred to the next prompt.  
> **Rule**: Zero `sync_to_async` wrapping. Every async function is natively async end-to-end.

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT REQUEST                           │
├──────────────────────┬──────────────────────────────────────┤
│   DRF (Sync)         │   Django Ninja (Async)               │
│   /api/v1/auth/...   │   /api/v2/auth/...                  │
├──────────────────────┼──────────────────────────────────────┤
│ Serializers (DRF)    │ Pydantic Schemas (Ninja)             │
├──────────────────────┼──────────────────────────────────────┤
│ sync_views.py        │ async_views.py                       │
├──────────────────────┼──────────────────────────────────────┤
│ SyncRegistrationSvc  │ AsyncRegistrationSvc                 │
│ OTPService (sync)    │ OTPService (async)                   │
├──────────────────────┴──────────────────────────────────────┤
│            apps/common (shared utilities)                    │
│  ┌─────────────┬──────────────┬─────────────┬─────────────┐ │
│  │ utils.py    │ EmailManager │ SMSManager  │ Celery Tasks│ │
│  │ encrypt_otp │ send_mail    │ send_sms    │ send_email  │ │
│  │ decrypt_otp │ asend_mail   │ asend_sms   │ send_sms    │ │
│  │ redis_conn  │ (to_thread)  │ (to_thread) │ (background)│ │
│  └─────────────┴──────────────┴─────────────┴─────────────┘ │
├─────────────────────────────────────────────────────────────┤
│            admin_backend (DB-configured)                     │
│  ┌──────────────────────────┬───────────────────────────┐   │
│  │ DatabaseConfiguredEmail  │ DatabaseConfiguredSMS     │   │
│  │ Backend (SMTP/Mailgun/   │ Backend (Twilio/Termii)   │   │
│  │ SendGrid/ZeptoMail)      │                           │   │
│  └──────────────────────────┴───────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  UnifiedUser Model + CustomUserManager                       │
│  create_user() (sync)  |  acreate_user() (async)            │
└─────────────────────────────────────────────────────────────┘
```

---

## Existing Components Inventory (What's Already Built)

| Component | File | Sync | Async | Status |
|---|---|---|---|---|
| `UnifiedUser` Model | `authentication/models.py` | ✅ | ✅ `asave()` | ✅ Ready |
| `CustomUserManager` | `authentication/managers.py` | ✅ `create_user` | ✅ `acreate_user` | ✅ Ready |
| `UserRegistrationSerializer` | `authentication/serializers.py` | ✅ | ❌ (calls `sync_to_async`) | ⚠️ Fix |
| `OTPSerializer` | `authentication/serializers.py` | ✅ | ✅ | ✅ Ready |
| `RegistrationSchema` (Pydantic) | `authentication/types/auth_schemas.py` | — | ✅ | ⚠️ Fix `user_id` type |
| `OTPService.generate_otp_sync` | `authentication/services/otp_service.py` | ✅ | ❌ (uses `sync_to_async`) | ⚠️ Rewrite |
| `OTPService.verify_otp_sync` | `authentication/services/otp_service.py` | ✅ | ❌ (uses `sync_to_async`) | ⚠️ Rewrite |
| `OTPService.resend_otp_sync` | `authentication/services/otp_service.py` | ✅ | ⚠️ (partial, mixes) | ⚠️ Rewrite |
| `RegistrationService.register_sync` | `authentication/services/registration_service.py` | ✅ | ❌ (uses `sync_to_async`) | ⚠️ Rewrite |
| `EmailManager` | `common/managers/email.py` | ✅ `send_mail` | ✅ `asend_mail` (to_thread) | ✅ Ready |
| `SMSManager` | `common/managers/sms.py` | ✅ `send_sms` | ✅ `asend_sms` (to_thread) | ✅ Ready |
| `CustomJSONRenderer` | `common/renderers.py` | ✅ | ✅ | ✅ Ready |
| Celery Tasks (`send_email_task`) | `authentication/tasks.py` | ✅ | — | ✅ Ready |
| `BurstRateThrottle` | `authentication/throttles.py` | ✅ | ✅ | ✅ Ready |
| DRF Sync Views | `apis/auth_views/sync_views.py` | ✅ | — | ⚠️ Enhance |
| Ninja Async Views | `apis/auth_views/async_views.py` | — | ✅ | ⚠️ Enhance |

---

## What the Legacy Code Does (Pattern We Must Match)

The old `RegisterViewCelery` in `userauths/views.py` follows this battle-tested flow:

```
1. @transaction.atomic decorator
2. Validate via serializer.is_valid(raise_exception=True)
3. serializer.save() → creates User with is_active=False
4. Generate 6-digit OTP → encrypt_otp() → encrypted string
5. get_redis_connection_safe() → check Redis is alive (or rollback)
6. Store in Redis: key="otp_data:{user_id}:{encrypted_otp}", value=str({'user_id': id, 'otp': encrypted_otp}), TTL=300
7. Send via Celery: signature('userauths.tasks.send_email_task', args=(subject, [email], template, context)).apply_async()
   OR send_sms_task.delay(phone, body)
8. Return 201 with human-readable message
9. Exception → transaction.set_rollback(True) → 500 with human message
```

---

## ⚠️ CRITICAL RULE: No `sync_to_async` Wrapping

Per user's explicit instruction:
- **❌ FORBIDDEN**: `sync_to_async(func)()`, `database_sync_to_async`, any wrapping of sync → async
- **✅ ALLOWED**: `asyncio.to_thread()` ONLY for non-Django I/O (Redis, SMTP, Twilio HTTP calls)
- **✅ ALLOWED**: Django's native async: `await Model.objects.acreate()`, `await qs.afirst()`, `await obj.asave()`
- **✅ REQUIRED**: Every async function must be 100% async from first line to last line

---

## 🔧 STEP 1: Fix `OTPService` — Pure Async Methods

**File**: `apps/authentication/services/otp_service.py`

### What Changes:
- **Rewrite** `generate_otp_async()` — remove `sync_to_async`, use `asyncio.to_thread` for Redis only
- **Rewrite** `verify_otp_async()` — remove `sync_to_async`, use `asyncio.to_thread` for Redis only
- **Rewrite** `resend_otp_async()` — remove `sync_to_async` calls, use native async ORM + `asyncio.to_thread` for Redis

### Sync Methods: Keep exactly as-is (no changes)

### New Async `generate_otp_async`:
```python
@staticmethod
async def generate_otp_async(user_id, purpose='verify') -> str:
    """Natively async OTP generation. No sync_to_async."""
    import asyncio
    
    # 1. Generate OTP (CPU-bound, instant — no wrapping needed)
    otp = generate_numeric_otp()
    
    # 2. Encrypt OTP (CPU-bound, instant — no wrapping needed)
    encrypted_otp = encrypt_otp(otp)
    
    # 3. Store in Redis (network I/O — use asyncio.to_thread)
    async def _store_in_redis():
        redis_conn = get_redis_connection_safe()
        if not redis_conn:
            raise Exception("Redis unavailable")
        snippet = encrypted_otp[:16]
        redis_key = f"otp:{user_id}:{purpose}:{snippet}"
        redis_conn.setex(redis_key, 300, encrypted_otp)
    
    await asyncio.to_thread(_store_in_redis)  # ← asyncio.to_thread, NOT sync_to_async
    
    logger.info(f"OTP generated (async) for User {user_id}")
    return otp
```

### New Async `verify_otp_async`:
```python
@staticmethod
async def verify_otp_async(user_id, otp, purpose='verify') -> bool:
    """Natively async OTP verification. No sync_to_async."""
    import asyncio
    
    async def _verify_in_redis():
        redis_conn = get_redis_connection_safe()
        if not redis_conn:
            raise Exception("Redis unavailable")
        pattern = f"otp:{user_id}:{purpose}:*"
        keys = redis_conn.keys(pattern)
        for key in keys:
            stored = redis_conn.get(key)
            if not stored:
                continue
            decrypted = decrypt_otp(stored.decode())
            if decrypted == otp:
                redis_conn.delete(key)
                return True
        return False
    
    result = await asyncio.to_thread(_verify_in_redis)
    if result:
        logger.info(f"OTP Verified (async) for User {user_id}")
    else:
        logger.warning(f"OTP Verification Failed (async) for User {user_id}")
    return result
```

### New Async `resend_otp_async`:
```python
@staticmethod
async def resend_otp_async(email_or_phone, purpose='verify') -> str:
    """Natively async OTP resend. Uses native Django async ORM."""
    import asyncio
    
    # 1. Find User (native async ORM)
    user = None
    if '@' in email_or_phone:
        user = await UnifiedUser.objects.filter(email=email_or_phone).afirst()
    else:
        user = await UnifiedUser.objects.filter(phone=email_or_phone).afirst()
    
    if not user:
        return "If an account exists, a new OTP has been sent."
    
    # 2. Invalidate Old OTPs (Redis I/O via to_thread)
    async def _invalidate_old():
        redis_conn = get_redis_connection_safe()
        if redis_conn:
            pattern = f"otp:{user.id}:{purpose}:*"
            keys = redis_conn.keys(pattern)
            for key in keys:
                redis_conn.delete(key)
    await asyncio.to_thread(_invalidate_old)
    
    # 3. Generate New OTP (calls our fixed async method)
    otp = await OTPService.generate_otp_async(user.id, purpose)
    
    # 4. Dispatch (EmailManager.asend_mail / SMSManager.asend_sms — already async)
    if user.email:
        await EmailManager.asend_mail(
            subject="Resend Verification OTP",
            recipients=[user.email],
            template_name='otp.html',
            context={'user_id': str(user.id), 'otp': otp}
        )
    elif user.phone:
        await SMSManager.asend_sms(str(user.phone), f"Your new OTP: {otp}")
    
    return "If an account exists, a new OTP has been sent."
```

---

## 🔧 STEP 2: Fix `RegistrationService` — Pure Async Method

**File**: `apps/authentication/services/registration_service.py`

### What Changes:
- **Keep** `register_sync()` exactly as-is (it works perfectly)
- **Rewrite** `register_async()` — remove `sync_to_async`, build natively async using `acreate_user()` + async OTP + async Email/SMS
- **Remove** `from asgiref.sync import sync_to_async` import

### New Async `register_async`:
```python
@staticmethod
async def register_async(email=None, phone=None, password=None, 
                         role='client', request=None, **extra_fields) -> Dict[str, Any]:
    """
    Natively Async User Registration Flow (Django Ninja / ASGI).
    Uses Django's native async ORM — ZERO sync_to_async.
    """
    import asyncio
    
    try:
        # Sanitize
        extra_fields.pop('password_confirm', None)
        extra_fields.pop('password2', None)
        
        # 1. Create User (native async via CustomUserManager.acreate_user)
        user = await UnifiedUser.objects.acreate_user(
            email=email,
            phone=phone,
            password=password,
            role=role,
            is_active=False,
            is_verified=False,
            **extra_fields
        )
        logger.info(f"✅ User created (Async): {email or phone} (ID: {user.id})")
        
        # 2. Generate OTP (our fixed async method)
        otp = await OTPService.generate_otp_async(user.id, purpose='verify')
        
        # 3. Send Notification (EmailManager.asend_mail / SMSManager.asend_sms)
        if email:
            await EmailManager.asend_mail(
                subject="Verify Your Email",
                recipients=[email],
                template_name='otp.html',
                context={'user_id': str(user.id), 'otp': otp}
            )
            logger.info(f"✅ OTP email sent (async) to {email}")
        elif phone:
            await SMSManager.asend_sms(str(phone), f"Your verification OTP: {otp}")
            logger.info(f"✅ OTP SMS sent (async) to {phone}")
        
        return {
            'message': 'Registration successful. Check email/phone for OTP.',
            'user_id': str(user.id),
            'email': email,
            'phone': str(phone) if phone else None
        }
        
    except Exception as e:
        logger.error(f"❌ Registration Failed (Async): {str(e)}", exc_info=True)
        raise e
```

> **Note**: No `transaction.atomic()` in async path. Django 6.0 doesn't support async atomic transactions natively. If the user creation succeeds but OTP/email fails, the user record stays with `is_active=False`, `is_verified=False` — harmless. They can re-register or request resend OTP.

---

## 🔧 STEP 3: Fix Pydantic Schemas + DRF Serializer `create()` Method

**File**: `apps/authentication/types/auth_schemas.py`

### Changes:
- `VerifyOTPSchema.user_id` type → change from `int` to `str` (UUID PK from `TimeStampedModel`)
- `RegistrationSchema` → Add `password2` alias for DRF compatibility (field is `password_confirm` currently). No breaking change.

**File**: `apps/authentication/serializers.py`

### Changes:
- `UserRegistrationSerializer.create()` → Fix the `**validated_data` double-pass bug (currently passes `email`, `phone`, `password`, `role` as kwargs AND inside `**validated_data` — duplicate argument error)
- `AsyncUserRegistrationSerializer.acreate()` → Remove `sync_to_async` wrapping, call `RegistrationService.register_async` properly

---

## 🔧 STEP 4: Perfect the Sync & Async Views

**File**: `apis/auth_views/sync_views.py`

### `RegisterView.post()` — Enhance to match legacy pattern:
```python
def post(self, request) -> Response:
    try:
        # 1. Validate
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        
        # 2. Service Call (sync, atomic inside service)
        result = RegistrationService.register_sync(
            email=validated.get('email'),
            phone=validated.get('phone'),
            password=validated['password'],
            role=validated['role']
        )
        
        return Response({
            "message": result['message'],
            "user_id": result['user_id'],
            "email": result.get('email'),
            "phone": result.get('phone')
        }, status=status.HTTP_201_CREATED)
    
    except serializers.ValidationError as e:
        logger.warning(f"Registration validation failed: {e}")
        return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"RegisterView Error: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred during registration. Please try again or contact support."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
```

### `VerifyOTPView.post()` — Add human-readable messages, match legacy:
```python
def post(self, request) -> Response:
    try:
        serializer = OTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        otp_code = serializer.validated_data['otp']
        user_id = request.data.get('user_id')
        
        if not user_id:
            return Response({"error": "User ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        valid = OTPService.verify_otp_sync(user_id, otp_code, purpose="verify")
        
        if not valid:
            return Response(
                {"error": "Invalid or expired OTP. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = UnifiedUser.objects.get(pk=user_id)
        if not user.is_active:
            user.is_active = True
        user.is_verified = True
        user.save()
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            "message": "Your account has been successfully verified.",
            "user_id": str(user.id),
            "role": user.role,
            "identifying_info": user.email if user.email else str(user.phone),
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_200_OK)
    
    except UnifiedUser.DoesNotExist:
        return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
    except serializers.ValidationError as e:
        return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"VerifyOTP Error: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred during verification. Please try again."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
```

---

**File**: `apis/auth_views/async_views.py`

### Ninja `register()` — Pass clean kwargs to service:
```python
@auth_router.post("/register", response={201: Dict[str, Any]}, auth=None)
async def register(request, data: RegistrationSchema):
    try:
        result = await RegistrationService.register_async(
            email=data.email,
            phone=data.phone,
            password=data.password,
            role=data.role,
        )
        return 201, result
    except Exception as e:
        logger.error(f"Async Register Error: {e}")
        from ninja.errors import HttpError
        raise HttpError(500, f"Registration failed: {str(e)}")
```

### Ninja `verify_otp()` — Fix token generation (move to `asyncio.to_thread`):
```python
@auth_router.post("/verify-otp", response={200: Dict[str, Any]}, auth=None)
async def verify_otp(request, data: VerifyOTPSchema):
    import asyncio
    
    valid = await OTPService.verify_otp_async(user_id=data.user_id, otp=data.otp)
    
    if not valid:
        from ninja.errors import HttpError
        raise HttpError(400, "Invalid or expired OTP. Please request a new one.")
    
    user = await UnifiedUser.objects.aget(pk=data.user_id)
    if not user.is_active:
        user.is_active = True
    user.is_verified = True
    await user.asave()
    
    # JWT generation is CPU-bound + not async-safe — use to_thread
    def _get_tokens():
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token), str(refresh)
    
    access, refresh = await asyncio.to_thread(_get_tokens)
    
    return 200, {
        "message": "Your account has been successfully verified.",
        "user_id": str(user.id),
        "role": user.role,
        "identifying_info": user.email if user.email else str(user.phone),
        "access": access,
        "refresh": refresh,
    }
```

---

## 🔧 STEP 5: Wire URLs + End-to-End Verification

**File**: `apps/authentication/urls.py`

### DRF (Sync) URL Patterns — `/api/v1/auth/`:
```python
urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),
]
```

### Ninja (Async) Router — `/api/v2/auth/`:
```python
# In ninja_api.py or main api.py
api.add_router("/v2/auth/", auth_router, tags=["Authentication V2"])
```

### Verification Checklist:
| Test | DRF Sync | Ninja Async |
|---|---|---|
| Register with email → 201 + message | ☐ | ☐ |
| Register with phone → 201 + message | ☐ | ☐ |
| Register with both → 400 error | ☐ | ☐ |
| Register with neither → 400 error | ☐ | ☐ |
| Duplicate email → 400 error | ☐ | ☐ |
| Password mismatch → 400 error | ☐ | ☐ |
| Verify OTP → 200 + JWT tokens | ☐ | ☐ |
| Wrong OTP → 400 human error | ☐ | ☐ |
| Expired OTP → 400 human error | ☐ | ☐ |
| Resend OTP → 200 new OTP sent | ☐ | ☐ |

---

## Summary of Files to Modify

| # | File | Action |
|---|---|---|
| 1 | `authentication/services/otp_service.py` | Rewrite 3 async methods (no `sync_to_async`) |
| 2 | `authentication/services/registration_service.py` | Rewrite `register_async` (no `sync_to_async`) |
| 3 | `authentication/types/auth_schemas.py` | Fix `user_id` type to `str` (UUID) |
| 4 | `authentication/serializers.py` | Fix `create()` double-pass bug |
| 5 | `authentication/apis/auth_views/sync_views.py` | Enhance `RegisterView`, `VerifyOTPView`, `ResendOTPView` |
| 6 | `authentication/apis/auth_views/async_views.py` | Enhance Ninja routes + ADRF views |
| 7 | `authentication/urls.py` | Verify/add URL patterns |
    