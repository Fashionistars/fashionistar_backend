# `apps/authentication` — Identity & Access Management

> **Version** 2026-03-19 · **Django** 6.0.2 · **Fashionistar Engineering**
>
> Enterprise-grade unified authentication system supporting email, phone, Google OAuth, and FIDO2/WebAuthn biometrics with JWT tokens, OTP verification, and soft-delete lifecycle tracking.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Quick Start](#quick-start)
3. [API Endpoints](#api-endpoints)
4. [Key Models](#key-models)
5. [Services Layer](#services-layer)
6. [Managers & Backends](#managers--backends)
7. [Admin Interface](#admin-interface)
8. [Registration Flow](#registration-flow)
9. [Error Handling](#error-handling)
10. [Integration Guide](#integration-guide)
11. [Testing](#testing)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  UnifiedUser — Single model for all user types     │
│  • Email + password                                 │
│  • Phone + OTP (Twilio)                             │
│  • Google OAuth 2.0                                 │
│  • FIDO2/WebAuthn biometrics                        │
├─────────────────────────────────────────────────────┤
│  JWT Authentication (SimpleJWT)                     │
│  • Access token (7 days)                            │
│  • Refresh token (configurable)                     │
│  • Token blacklisting on logout                     │
├─────────────────────────────────────────────────────┤
│  User Lifecycle Tracking                            │
│  • is_deleted flag (soft-delete, no data loss)      │
│  • UserLifecycleRegistry (login counts)             │
│  • LoginEvent records (IP, UA, device, geo)         │
├─────────────────────────────────────────────────────┤
│  Business Logic via EventBus                        │
│  • No Django signals for auth logic                 │
│  • event_bus.emit_on_commit('user.registered')      │
│  • Celery tasks for async notifications             │
└─────────────────────────────────────────────────────┘
```

**Design Philosophy:**
- **One model** (`UnifiedUser`) for clients, vendors, admins, support, editors, and assistants
- **Savepoint protection** — every `user.save()` wrapped in `transaction.atomic()` to prevent IntegrityError from poisoning outer transactions
- **Soft-delete aware** — `CustomUserManager` distinguishes active vs deleted users and raises typed exceptions
- **Event-driven** — business events via `EventBus`, never via Django signals

---

## Quick Start

### 1. Register a User (Email)

```bash
curl -X POST http://localhost:8000/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "StrongP@ss123!",
    "role": "client"
  }'
# Returns HTTP 201
# {
#   "success": true,
#   "message": "Registration successful. OTP sent.",
#   "data": {
#     "user_id": "550e8400-e29b-41d4-a716-446655440000",
#     "member_id": "FASTAR000001",
#     "role": "client"
#   }
# }
```

### 2. Verify OTP

```bash
# OTP arrives via email/SMS
curl -X POST http://localhost:8000/api/v1/auth/verify-otp/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "otp": "123456",
    "purpose": "verify"
  }'
```

### 3. Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "StrongP@ss123!"}'
# Returns HTTP 200
# {
#   "success": true,
#   "data": {
#     "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
#     "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
#   }
# }
```

### 4. Refresh Access Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."}'
```

### 5. Logout (Blacklist Token)

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout/ \
  -H "Authorization: Bearer eyJ0eXAi..." \
  -H "Content-Type: application/json" \
  -d '{"refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."}'
```

---

## API Endpoints

**Base URL:** `/api/v1/auth/`

| Method | Path | Purpose | Auth Required |
|---|---|---|---|
| `POST` | `/register/` | Create new user + send OTP | No |
| `POST` | `/verify-otp/` | Verify OTP + mark verified | No |
| `POST` | `/login/` | JWT login (access + refresh) | No |
| `POST` | `/token/refresh/` | Refresh access token | No |
| `POST` | `/logout/` | Blacklist refresh token | Yes |
| `POST` | `/password/change/` | Change password (authenticated) | Yes |
| `POST` | `/password/reset/` | Send password reset OTP | No |
| `POST` | `/password/reset/confirm/` | Confirm & set new password | No |

**Response Format (Standard JSON Envelope):**

```json
// Success (201/200)
{
  "success": true,
  "message": "Description of success",
  "data": { "key": "value" }
}

// Error (400/409/429)
{
  "success": false,
  "message": "Human-readable error",
  "code": "error_code",
  "errors": {
    "field": ["Validation error message"]
  }
}
```

---

## Key Models

### UnifiedUser

Central identity model for the entire platform. Extends `AbstractBaseUser` + `PermissionsMixin` + `SoftDeleteModel`.

| Field | Type | Description |
|---|---|---|
| `id` | UUIDField | Primary key, auto-generated |
| `email` | EmailField | Unique, nullable (phone-only users) |
| `phone` | PhoneNumberField | Unique, nullable (email-only users) |
| `member_id` | CharField | `FASTAR000001` format (auto-assigned) |
| `role` | CharField | `client` \| `vendor` \| `admin` \| `support` \| `editor` \| `assistant` |
| `auth_provider` | CharField | `email` \| `phone` \| `google` \| `webauthn` |
| `avatar` | URLField | Cloudinary `secure_url` (Cloudinary direct upload flow) |
| `password` | CharField | Hashed password (bcrypt) |
| `is_verified` | BooleanField | True after email/phone OTP verification |
| `is_deleted` | BooleanField | Soft-delete flag (from `SoftDeleteModel`) |
| `is_active` | BooleanField | Account active status |
| `created_at` | DateTimeField | Registration timestamp |
| `updated_at` | DateTimeField | Last modification timestamp |

**Required Fields for Login:**
- Email-based: `email` + `password`
- Phone-based: `phone` + `password`

**Avatar Upload Flow:**
Since avatar is a `URLField` (not `ImageField`), uploads use **two-phase Cloudinary direct upload**:
```
1. Frontend → POST /api/v1/upload/presign/ (with asset_type=avatar)
2. Cloudinary ← Direct upload (bypasses Django)
3. Cloudinary → POST /api/v1/upload/webhook/cloudinary/ (HMAC-SHA256 validated)
4. Celery task → Updates user.avatar = secure_url
```

### MemberIDCounter

Atomic counter for sequential member ID generation.

**How it works:**
```python
# Thread-safe F()-expression increment (no lock, no race):
counter = MemberIDCounter.objects.select_for_update().get_or_create(id=1)[0]
counter.counter = F('counter') + 1
counter.save(update_fields=['counter'])
counter.refresh_from_db()
member_id = f"FASTAR{counter.counter:06d}"
```

> [!IMPORTANT]
> `MemberIDCounter` is excluded from analytics signal tracking (in `_EXCLUDED_MODEL_NAMES`). This prevents feedback loops where every registration creates phantom "Update" events.

### BiometricCredential

Stores FIDO2/WebAuthn credentials per user.

| Field | Type | Description |
|---|---|---|
| `user` | FK → UnifiedUser | Owner |
| `credential_id` | BinaryField | FIDO2 credential ID |
| `public_key` | BinaryField | FIDO2 public key |
| `sign_count` | IntegerField | Replay attack counter |
| `created_at` | DateTimeField | Credential registration time |

### LoginEvent

Immutable record of every login.

| Field | Type | Description |
|---|---|---|
| `user` | FK → UnifiedUser | Who logged in |
| `ip_address` | GenericIPAddressField | Client IP |
| `user_agent` | TextField | Browser/device UA |
| `device_type` | CharField | `desktop` / `mobile` / `tablet` / `bot` |
| `country` | CharField | GeoIP country code |
| `login_type` | CharField | `email` / `phone` / `google` / `webauthn` |
| `created_at` | DateTimeField | Login timestamp |

---

## Services Layer

**Directory:** `apps/authentication/services/`

### Registration: `sync_service.py`

```python
from apps.authentication.services.registration.sync_service import register_sync

result = register_sync(validated_data={
    'email': 'user@example.com',
    'password': 'StrongP@ss123!',
    'role': 'client',
})
# Returns: { user: UnifiedUser, otp: str }
```

**Responsibilities:**
1. Atomic increment `MemberIDCounter.get_next_id()` → `FASTAR000001`
2. Create user inside `transaction.atomic()` (savepoint-wrapped)
3. Generate OTP via `OTPService.generate_otp_sync(user.id)`
4. Emit `EventBus.emit_on_commit('user.registered', user_uuid=..., role=...)`
5. Schedule Celery tasks via `transaction.on_commit()` for email/SMS delivery

### OTP Service: `otp_service.py`

```python
from apps.authentication.services.otp import OTPService

# Generate
otp = OTPService.generate_otp_sync(user_id, purpose='verify')

# Verify
is_valid = OTPService.verify_otp_sync(user_id, submitted_otp, purpose='verify')
# Raises: OTPExpiredError, OTPInvalidError, OTPMaxAttemptsError
```

**Storage:** Redis only (never in database). TTL configurable per purpose.

---

## Managers & Backends

**File:** `apps/authentication/managers.py` + `backends.py`

### CustomUserManager

Soft-delete aware, savepoint-protected user creation.

| Feature | Implementation |
|---|---|
| Default queryset | Excludes `is_deleted=True` |
| `.all_with_deleted()` | Includes soft-deleted users |
| `.deleted_only()` | Only soft-deleted users |
| Savepoint pattern | `user.save()` wrapped in nested `transaction.atomic()` |
| Typed UNIQUE errors | `DuplicateUserError` vs `SoftDeletedUserExistsError` |
| Async parity | `acreate_user()` / `acreate_superuser()` with `async with transaction.atomic()` |

**Savepoint Pattern (prevents IntegrityError from poisoning outer TX):**
```python
try:
    with transaction.atomic():   # savepoint
        user.save(using=self._db)
    return user
except IntegrityError as exc:
    # Outer TX healthy — safe to SELECT
    existing = self.all_with_deleted().filter(...).first()
    if existing and existing.is_deleted:
        raise SoftDeletedUserExistsError() from exc
    raise DuplicateUserError() from exc
```

### Authentication Backends

| Backend | File | Description |
|---|---|---|
| `SoftDeleteAwareModelBackend` | `backends.py` | Default Django backend; handles soft-deleted users gracefully |
| `UnifiedUserBackend` | `backends.py` | Email/phone authentication with `SoftDeletedUserError` handling |

```python
# settings.py
AUTHENTICATION_BACKENDS = [
    'apps.authentication.backends.SoftDeleteAwareModelBackend',
]
```

---

## Admin Interface

**File:** `apps/authentication/admin.py`

### UnifiedUserAdmin (1800+ lines)

The admin includes:
- **Import/Export** — Streaming CSV/XLSX/JSON (100k+ rows, no OOM)
- **Idempotent Bulk Import** — UPSERT with `SELECT FOR UPDATE`
- **Audit Trail** — Every save/delete logged via `AuditedModelAdmin` mixin
- **Role-Based Access** — Superuser / Staff / Support tiers
- **Color-coded Badges** — Role, status, verification, soft-delete
- **Avatar Thumbnails** — 40×40 circular images in changelist
- **Bulk Actions** — soft_delete, restore, hard_delete (superuser only)
- **Advanced Search** — email, phone, member_id, role filters
- **Read-only Fields** — id, member_id, created_at, updated_at

> [!NOTE]
> `UnifiedUserAdmin.changelist_view()` resolves Django admin MRO conflicts between `SoftDeleteAdminMixin` and `BaseUserAdmin`.

---

## Registration Flow

```
1. Client POST /api/v1/auth/register/
   ├─ Body: { email, password, role }
   └─ RegistrationSerializer.validate()
      ├─ Email/phone normalization
      ├─ Password strength check (zxcvbn score ≥ 2)
      └─ Role validation

2. register_sync(validated_data)
   ├─ START transaction.atomic()
   │  ├─ MemberIDCounter.get_next_id() → FASTAR000001
   │  ├─ CustomUserManager.create_user()
   │  │  └─ Savepoint: user.save() [catches IntegrityError]
   │  └─ OTPService.generate_otp_sync(user.id)
   ├─ EventBus.emit_on_commit('user.registered', ...)
   │  └─ [After TX commit] → Celery: upsert_user_lifecycle_registry
   └─ transaction.on_commit()
      └─ Celery: send_otp_email / send_otp_sms

3. Response HTTP 201
   {
     "success": true,
     "message": "Registration successful. OTP sent.",
     "data": {
       "user_id": "...",
       "member_id": "FASTAR000001",
       "role": "client"
     }
   }

4. Client POST /api/v1/auth/verify-otp/
   └─ OTPService.verify_otp_sync()
      └─ user.is_verified = True

5. Client POST /api/v1/auth/login/
   └─ Returns { access, refresh } JWT tokens
```

---

## Error Handling

**File:** `apps/authentication/exceptions.py`

All exceptions are mapped to standard JSON envelope by `apps.common.exceptions.custom_exception_handler`.

| Exception | HTTP Status | When Raised |
|---|---|---|
| `DuplicateUserError` | 400 | Email/phone belongs to active user |
| `SoftDeletedUserExistsError` | 409 | Email/phone belongs to soft-deleted user |
| `SoftDeletedUserError` | 403 | Soft-deleted user tries to log in |
| `OTPExpiredError` | 400 | OTP TTL exceeded (e.g., 15 min) |
| `OTPInvalidError` | 400 | OTP value mismatch |
| `OTPMaxAttemptsError` | 429 | Too many failed OTP attempts (rate limited) |

**Example error response:**
```json
{
  "success": false,
  "message": "A user with this email already exists.",
  "code": "duplicate_user_error",
  "errors": {
    "email": ["A user with this email already exists."]
  }
}
```

---

## Integration Guide

### Using Authentication in Your App

```python
from apps.authentication.models import UnifiedUser
from apps.common.permissions import IsVendor, IsClient

# In a DRF view
class ProductView(APIView):
    permission_classes = [IsAuthenticated, IsVendor]

    def get_queryset(self):
        return Product.objects.filter(vendor__user=self.request.user)
```

### Accessing User in Event Handlers

```python
# In any Celery task or event handler
from apps.authentication.models import UnifiedUser

user = UnifiedUser.objects.get(id=user_uuid)
# or with soft-delete awareness:
user = UnifiedUser.objects.all_with_deleted().get(id=user_uuid)
```

### Adding a New Role

1. Add role string to `UnifiedUser.ROLE_CHOICES` in `models.py`
2. Add corresponding permission class in `apps/common/permissions.py`
3. Update `apps/authentication/admin.py` if role-based admin filtering needed

### Subscribing to User Events

```python
# In your app's event handlers
from apps.common.events import event_bus

def on_user_registered_in_vendors(user_uuid, role, **kwargs):
    if role == 'vendor':
        VendorProfile.objects.get_or_create(user_id=user_uuid)

# In your app's apps.py ready()
event_bus.subscribe('user.registered', on_user_registered_in_vendors)
```

---

## Testing

### cURL Quick Tests

```bash
BASE=http://localhost:8000

# Register (expect 201)
curl -X POST $BASE/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Secure@2026!","role":"client"}'

# Register duplicate (expect 400, NOT 500)
curl -X POST $BASE/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Another@2026!","role":"client"}'

# Login (expect 200 with tokens)
curl -X POST $BASE/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Secure@2026!"}'
```

### Admin Tests

1. **UnifiedUser admin** → select users → "Stream export" → CSV downloads (no `AttributeError`)
2. **Model Analytics** → `MemberIDCounter` row's `Updates` stays at 0 after registrations
3. **Soft delete** → soft-delete user → try login → expect 403 (not 404)
4. **Import/Export** → Import CSV with 1000+ rows → verify UPSERT works

### Automated Tests

```bash
uv run manage.py test apps.authentication.tests -v 2
```

---

## File Structure

```
apps/authentication/
├── __init__.py
├── admin.py                    # UnifiedUserAdmin (1800+ lines)
├── apps.py                     # Config
├── backends.py                 # SoftDeleteAwareModelBackend, UnifiedUserBackend
├── exceptions.py               # DuplicateUserError, OTPExpiredError, etc.
├── managers.py                 # CustomUserManager (savepoint-protected)
├── models.py                   # UnifiedUser, MemberIDCounter, BiometricCredential, LoginEvent
├── serializers.py              # RegistrationSerializer, LoginSerializer, etc.
├── urls.py                     # DRF URL routing (/api/v1/auth/)
├── views.py                    # DRF views (RegisterView, LoginView, LogoutView, etc.)
├── services/
│   ├── __init__.py
│   ├── registration/
│   │   └── sync_service.py    # register_sync()
│   └── otp/
│       └── otp_service.py     # OTPService (Redis-backed, no DB)
├── tasks.py                    # Celery: send_otp_email, send_otp_sms
├── signals.py                  # Post-save signals (analytics only, no business logic)
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_apis.py
    ├── test_services.py
    └── test_admin.py
```

---

**Last updated:** 2026-03-19 · **Maintainer:** Fashionistar Engineering
