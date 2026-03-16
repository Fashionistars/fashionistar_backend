# apps/authentication — Developer Reference

> **Version** 2026-03-16 · **Django** 6.0.2 · **Maintainer** Fashionistar Engineering

This document is the canonical reference for every component in `fashionistar_backend/apps/authentication`. Read it fully before adding or modifying anything in this app.

---

## Table of Contents

1. [Overview & Design Philosophy](#overview--design-philosophy)
2. [Architecture Diagram](#architecture-diagram)
3. [URL Routing](#url-routing)
4. [Models](#models)
   - [UnifiedUser](#unifieduser)
   - [MemberIDCounter](#memberidcounter)
   - [UserDevice](#userdevice)
5. [Managers](#managers)
6. [Admin](#admin)
7. [APIs (DRF Sync)](#apis-drf-sync)
8. [APIs (Django Ninja Async)](#apis-django-ninja-async)
9. [Services Layer](#services-layer)
10. [Registration Flow — Step by Step](#registration-flow--step-by-step)
11. [Error Handling](#error-handling)
12. [Integration for Future Apps](#integration-for-future-apps)
13. [Testing Checklist](#testing-checklist)

---

## Overview & Design Philosophy

`apps.authentication` owns the entire user identity layer:

- **One model** (`UnifiedUser`) for all user types (client, vendor, admin, support, editor, assistant).
- **Two API stacks**: synchronous DRF at `/api/v1/auth/` and asynchronous Django Ninja at `/api/v1/ninja/auth/`.
- **No Django signals for business logic** — lifecycle events are emitted via `EventBus` and handled in `apps.common.event_handlers`.
- **UNIQUE constraint protection** — a nested savepoint (not a full transaction) wraps every `user.save()` so an IntegrityError never poisons the outer transaction.
- **Soft-delete aware** — `CustomUserManager` distinguishes between duplicate-active vs duplicate-soft-deleted users and raises typed exceptions accordingly.

---

## Architecture Diagram

```
POST /api/v1/auth/register/
        │
        ▼
   RegisterView (DRF GenericAPIView)
        │
        ▼
   RegistrationSerializer.validate()
   [phone normalization, password strength, email uniqueness]
        │
        ▼
   register_sync(validated_data)   [sync_service.py]
        │
        ├─► transaction.atomic()
        │       ├─► MemberIDCounter.get_next_id()  [F()-safe atomic ++]
        │       ├─► UnifiedUser.objects.create_user()
        │       │       └─► with transaction.atomic():  ← savepoint
        │       │               user.save()
        │       │       except IntegrityError → DuplicateUserError / SoftDeletedUserExistsError
        │       └─► OTPService.generate_otp_sync(user.id)
        │
        ├─► EventBus.emit_on_commit('user.registered', user_uuid=..., role=...)
        │       └── [after TX commit] on_user_registered() → Celery: upsert_user_lifecycle_registry
        │
        ├─► transaction.on_commit → send_otp_email / send_otp_sms (Celery)
        │
        └─► return 201 { success, message, data: {user_id, member_id, role} }
```

---

## URL Routing

**File:** `apps/authentication/urls.py`

### Versioning Rule

> All endpoints — DRF and Ninja — are on **v1**. Ninja uses `/api/v1/ninja/` to avoid URL collision with DRF at `/api/v1/`.

### DRF Synchronous Endpoints (`/api/v1/auth/`)

| Method | Path | View | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/auth/register/` | `RegisterView` | Create new user + send OTP |
| `POST` | `/api/v1/auth/verify-otp/` | `VerifyOTPView` | Verify OTP + mark user verified |
| `POST` | `/api/v1/auth/login/` | `LoginView` | JWT login (access + refresh) |
| `POST` | `/api/v1/auth/token/refresh/` | simplejwt `TokenRefreshView` | Refresh access token |
| `POST` | `/api/v1/auth/logout/` | `LogoutView` | Blacklist refresh token |
| `POST` | `/api/v1/auth/password/change/` | `PasswordChangeView` | Authenticated password change |
| `POST` | `/api/v1/auth/password/reset/` | `PasswordResetView` | Send reset OTP |
| `POST` | `/api/v1/auth/password/reset/confirm/` | `PasswordResetConfirmView` | Confirm + set new password |

### Django Ninja Async Endpoints (`/api/v1/ninja/auth/`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/ninja/auth/register` | Async registration (ASGI, high-concurrency) |
| `POST` | `/api/v1/ninja/auth/login` | Async JWT login |

> [!NOTE]
> Ninja endpoints are served at the `/api/v1/ninja/auth/` prefix. **All future Ninja endpoints for any app MUST use `/api/v1/ninja/<app>/` to stay consistent.**

---

## Models

### UnifiedUser

**File:** `apps/authentication/models.py`

Central identity model for the entire platform. Extends `AbstractBaseUser` + `PermissionsMixin` + `SoftDeleteModel`.

#### Key Fields

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField` (primary key) | UUID4, auto-generated |
| `email` | `EmailField` | Unique, nullable (phone-only users) |
| `phone` | `PhoneNumberField` | Unique, nullable (email-only users) |
| `member_id` | `CharField` | `'FASTAR000001'` format, auto-assigned |
| `role` | `CharField` | `'client'` \| `'vendor'` \| `'admin'` \| `'support'` \| `'editor'` \| `'assistant'` |
| `auth_provider` | `CharField` | `'email'` \| `'phone'` \| `'google'` |
| `avatar` | `URLField` | Cloudinary `secure_url` — set via `/api/v1/upload/presign/` flow |
| `is_verified` | `BooleanField` | True after OTP verification |
| `is_deleted` | `BooleanField` | Soft-delete flag (from `SoftDeleteModel`) |

#### Required Fields for Login

- Email-based: `email` + `password`
- Phone-based: `phone` + `password`

#### Avatar Upload

Since the avatar is a `URLField`, uploads go through the **two-phase Cloudinary** pattern:
1. Frontend calls `POST /api/v1/upload/presign/` with `asset_type=avatar` → gets signature
2. Frontend uploads file directly to Cloudinary (bypasses Django server)
3. Cloudinary calls `POST /api/v1/upload/webhook/cloudinary/` → Celery task updates `user.avatar`

To set via admin: paste any `https://res.cloudinary.com/...` URL directly.

---

### MemberIDCounter

**File:** `apps/authentication/models.py`

Atomic counter used to generate sequential member IDs (`FASTAR000001` → `FASTAR000002` etc.).

> [!IMPORTANT]
> `MemberIDCounter` is excluded from `ModelAnalytics` signal tracking (it's in `_EXCLUDED_MODEL_NAMES`). This prevents a feedback loop where every user registration causes phantom "Update" analytics entries.

**How it works:**
```python
# Thread-safe F()-expression increment (no lock, no race):
counter = MemberIDCounter.objects.select_for_update().get_or_create(id=1)[0]
counter.counter = F('counter') + 1
counter.save(update_fields=['counter'])
counter.refresh_from_db()
member_id = f"FASTAR{counter.counter:06d}"
```

---

### UserDevice

**File:** `apps/authentication/models.py`

Stores trusted devices per user for device-based 2FA/session tracking.

---

## Managers

**File:** `apps/authentication/managers.py`

### `CustomUserManager`

Key behaviors:

| Feature | Implementation |
|---|---|
| Soft-delete aware queries | Default `.objects` excludes `is_deleted=True` |
| `all_with_deleted()` | Returns all users including soft-deleted |
| Savepoint-safe UNIQUE guard | `user.save()` wrapped in `with transaction.atomic()` (nested savepoint) |
| Typed UNIQUE exceptions | `DuplicateUserError` vs `SoftDeletedUserExistsError` |
| Async parity | `acreate_user()` / `acreate_superuser()` use `asave()` with `async with transaction.atomic()` |

> [!IMPORTANT]
> **Savepoint pattern**: The nested `with transaction.atomic()` around `user.save()` creates a **savepoint** (not a full transaction). If `save()` raises `IntegrityError`, only the savepoint rolls back — the outer transaction stays healthy. This prevents `TransactionManagementError` in the `except` block's SELECT clause.

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

---

## Admin

**File:** `apps/authentication/admin.py`

### `UnifiedUserAdmin`

- Inherits `SoftDeleteAdminMixin` + `EnterpriseImportExportMixin` + `BaseUserAdmin`
- Custom form: `UnifiedUserAdminForm` (merged creation+change form — no "required field" errors when editing)
- Bulk actions: `soft_delete_selected`, `restore_selected`, `hard_delete_selected`
- **CSV/XLSX streaming export** — 100K+ users with no OOM
- Atomic import with dry-run preview

> [!NOTE]
> The `UnifiedUserAdmin.changelist_view()` overrides both `SoftDeleteAdminMixin` and `BaseUserAdmin` to resolve the Django admin MRO conflict.

---

## APIs (DRF Sync)

**File:** `apps/authentication/apis/auth_views/sync_views.py`

All endpoints follow the standard JSON envelope format from `apps.common.renderers`:

```json
// Success (201)
{
  "success": true,
  "message": "Registration successful. OTP sent.",
  "data": { "user_id": "uuid", "member_id": "FASTAR000001", "role": "client" }
}

// Error (400)
{
  "success": false,
  "message": "Validation error",
  "code": "validation_error",
  "errors": { "email": ["A user with this email already exists."] }
}
```

---

## APIs (Django Ninja Async)

**File:** `apps/authentication/apis/auth_views/async_views.py`
**Mount:** `POST /api/v1/ninja/auth/register`, `POST /api/v1/ninja/auth/login`

- ASGI-native, uses `async def` views with `await UnifiedUser.objects.acreate_user()`
- Same `DuplicateUserError` / `SoftDeletedUserExistsError` handling as sync
- Registered under `urls_namespace='authentication_v1'` in `ninja_api.py`

---

## Services Layer

**Directory:** `apps/authentication/services/`

### Registration: `sync_service.py`

```python
from apps.authentication.services.registration.sync_service import register_sync

result = register_sync(validated_data={
    'email': 'user@example.com',
    'password': 'strongpassword',
    'role': 'client',
})
# Returns: { user, otp }
```

**Responsibilities:**
1. Call `MemberIDCounter.get_next_id()`
2. Call `UnifiedUser.objects.create_user()` inside `transaction.atomic()`
3. Call `OTPService.generate_otp_sync(user.id)`
4. Emit `event_bus.emit_on_commit('user.registered', ...)` (replaces Django signal)
5. Schedule OTP delivery Celery task via `transaction.on_commit()`

### OTP: `otp_service.py`

```python
from apps.authentication.services.otp import OTPService

otp = OTPService.generate_otp_sync(user_id, purpose='verify')
is_valid = OTPService.verify_otp_sync(user_id, submitted_otp, purpose='verify')
```

OTPs stored in Redis with TTL. Never stored in the database.

---

## Registration Flow — Step by Step

```
1. Client → POST /api/v1/auth/register/
   Body: { email, password, role }

2. RegisterView → RegistrationSerializer.validate()
   - Normalize email / phone
   - Check password strength (zxcvbn score ≥ 2)
   - Validate role is allowed

3. register_sync(validated_data)
   a. MemberIDCounter.get_next_id() → "FASTAR000001"
   b. transaction.atomic():
      - create_user() [savepoint around user.save()]
      - OTPService.generate_otp_sync()
   c. event_bus.emit_on_commit('user.registered', ...)
   d. transaction.on_commit(): send_otp_email.apply_async()

4. Return HTTP 201:
   { success, message, data: { user_id, member_id, role } }

OTP sent to email / phone (Celery, fire-and-forget).

5. Client → POST /api/v1/auth/verify-otp/
   Body: { user_id, otp, purpose: "verify" }
   → OTPService.verify_otp_sync() → user.is_verified = True

6. Client → POST /api/v1/auth/login/
   → Returns { access, refresh } JWT tokens
```

---

## Error Handling

**File:** `apps/authentication/exceptions.py`

| Exception | HTTP Status | When raised |
|---|---|---|
| `DuplicateUserError` | 400 | Email/phone belongs to an active user |
| `SoftDeletedUserExistsError` | 409 | Email/phone belongs to a soft-deleted user |
| `SoftDeletedUserError` | 403 | Soft-deleted user tries to log in |
| `OTPExpiredError` | 400 | OTP TTL exceeded |
| `OTPInvalidError` | 400 | OTP value mismatch |
| `OTPMaxAttemptsError` | 429 | Too many wrong OTP attempts |

All exceptions are mapped to the standard JSON envelope by `apps.common.exceptions.custom_exception_handler`.

---

## Integration for Future Apps

### Checking user identity in any app

```python
from apps.authentication.models import UnifiedUser
from apps.common.permissions import IsVendor, IsClient

# In a DRF view
class ProductView(APIView):
    permission_classes = [IsAuthenticated, IsVendor]

    def get_queryset(self):
        return Product.objects.filter(vendor__user=self.request.user)
```

### Accessing user from event payload

```python
# In any event handler or Celery task receiving user_uuid
from apps.authentication.models import UnifiedUser

user = UnifiedUser.objects.get(id=user_uuid)
# or with soft-delete awareness:
user = UnifiedUser.objects.all_with_deleted().get(id=user_uuid)
```

### Adding a new role

1. Add the role string to `UnifiedUser.ROLE_CHOICES` in `models.py`
2. Add the corresponding permission class in `apps/common/permissions.py`
3. Update `apps/authentication/admin.py` if role-based admin filtering is needed

### Subscribing to user events

```python
# In your app's event handlers
from apps.common.events import event_bus

def on_user_registered_in_orders(user_uuid, role, **kwargs):
    if role == 'vendor':
        VendorProfile.objects.get_or_create(user_id=user_uuid)

# In your app's apps.py ready()
event_bus.subscribe('user.registered', on_user_registered_in_orders)
```

---

## Testing Checklist

Use these to validate after any change to this app:

### cURL Quick Tests

```bash
BASE=http://localhost:8000

# Register new user (expect 201)
curl -X POST $BASE/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Secure@2026!","role":"client"}'

# Register same email again (expect 400, NOT 500)
curl -X POST $BASE/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Another@2026!","role":"client"}'

# Ninja async register (expect 201 or 200)
curl -X POST $BASE/api/v1/ninja/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"ninja@example.com","password":"Secure@2026!","role":"vendor"}'
```

### Admin Page Tests

1. **UnifiedUser admin** → select users → "Stream export" → expect CSV download (no `AttributeError`)
2. **Model Analytics** → `MemberIDCounter` row's `Updates` column should stay at 0 after new registrations
3. **Soft delete** → soft-delete a user → try to log in → expect 403 (not 404)

### Automated Tests

```bash
uv run manage.py test apps.authentication.tests -v 2
```

---
**End of Document** · Last updated 2026-03-16
