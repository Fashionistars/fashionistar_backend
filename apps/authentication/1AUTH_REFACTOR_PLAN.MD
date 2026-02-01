# AUTHENTICATION REFACTOR EXECUTION PLAN (V1.0)

**Objective:** Implement "Industrial Enterprise Grade" Dual-Engine Authentication (Sync DRF + Async Ninja).
**Legacy Source:** `userauths` (to be deprecated).
**Target Destination:** `apps/authentication/`.

---

## 🏗️ SECTION 1: REGISTRATION (DUAL-ENGINE)

### Step 1: Centralized Service & Schema Definition

- **Goal:** Decouple business logic from views. Move registration logic to a unified Service Layer.
- **Actions:**
  - Create `apps/authentication/services/registration_service.py`:
    - Implement `create_user_atomic()`: Handles transactional user creation.
    - Implement `trigger_otp_flow()`: Calls `OTPService` and dispatches Event.
  - Define Pydantic Schemas in `apps/authentication/types/auth_types.py`:
    - `UserRegistrationSchema`: Strict typing for Ninja (Email/Phone validation).
  - **Architecture Check:** Ensure usage of `apps/common/utils.py` for logging and error handling.

### Step 2: Async Registration (Django Ninja)

- **Goal:** High-concurrency registration endpoint (~50ms target).
- **Actions:**
  - Create/Update `apps/authentication/apis/auth_views/async_views.py`.
  - **Logic:**
    - Use `asyncio.gather()` for parallel tasks (e.g., checking uniqueness of email & phone simultaneously).
    - Call `RegistrationService` (async wrapper or native async method).
    - Emit `UserRegisteredEvent` via `EventBus` (replacing signals).
  - **Validation:** Strict Pydantic validation (No `rest_framework.serializers` in async path).

### Step 3: Sync Registration (DRF)

- **Goal:** Admin/Legacy compatibility and standard web form support.
- **Actions:**
  - Create/Update `apps/authentication/apis/auth_views/sync_views.py`.
  - **Logic:**
    - Use `transaction.atomic()` decorator.
    - Call `RegistrationService` (sync method).
    - Return standard DRF responses.
  - **Validation:** Keep `UserRegistrationSerializer` for DRF navigability.

---

## 🔐 SECTION 2: OTP VERIFICATION & RESEND

### Step 4: OTP Service Construction (The Core)

- **Goal:** Centralize robust OTP handling with Redis encryption.
- **Actions:**
  - Create `apps/authentication/services/otp_service.py`:
    - Integrate `generate_numeric_otp` and `encrypt_otp` from `apps/common/utils.py`.
    - Implement `store_otp_safe()`: Uses `get_redis_connection_safe` with retries.
    - Implement `verify_otp_logic()`: Handles decryption and user lookups (optimized `scan_iter`).
  - **Backend:** Ensure `apps/common/providers/django_redis.py` is the simplified interface.

### Step 5: Verify & Resend Endpoints (Sync + Async)

- **Goal:** Secure, idempotent OTP verification.
- **Actions:**
  - **Async (`apis/auth_views/async_views.py`)**:
    - `POST /verify-otp/`: Async Ninja route. Fast validation.
    - `POST /resend-otp/`: Async dispatch of SMS/Email task.
  - **Sync (`apis/auth_views/sync_views.py`)**:
    - `VerifyOTPView` (GenericAPIView): Standard DRF implementation.
    - `ResendOTPView`: Standard DRF implementation.

---

## 🔑 SECTION 3: LOGIN & GOOGLE AUTH

### Step 6: Dual-Engine Login Architecture

- **Goal:** Unified login for Email/Phone with JWT issuance.
- **Actions:**
  - **Service:** `apps/authentication/services/auth_service.py` -> `authenticate_user()` method.
  - **Async Login (`async_views.py`)**:
    - Native `aget()` calls for user lookup.
    - Async JWT generation (manual encode or wrapped SimpleJWT).
  - **Sync Login (`sync_views.py`)**:
    - Standard `TokenObtainPairView` customization.
  - **Security:** Enforce rate-limiting (throttling) on both engines.

### Step 7: Google Auth Integration

- **Goal:** Social Auth without `django-allauth` bloat in async path.
- **Actions:**
  - Create `apps/authentication/services/google_service.py`.
  - **Async:** Use `httpx` or `aiohttp` to verify Google Tokens (non-blocking).
  - **Sync:** Use `requests` (blocking) for legacy/admin flows.
  - **Unified User Creation:** Both paths map to the same `get_or_create` logic in `RegistrationService`.

---

## 🔄 SECTION 4: PASSWORD MANAGEMENT

### Step 8: Password Reset Request (Dispatch)

- **Goal:** Securely initiate reset flow via Email or SMS.
- **Actions:**
  - **Service:** `apps/authentication/services/password_service.py` -> `initiate_reset()`.
  - **Logic:**
    - Determine Email vs Phone.
    - Generate Token (Email) or OTP (SMS).
    - Store in Redis (isolated keys `reset_flow:{id}`).
    - Dispatch `SendEmailTask` or `SendSMSTask` (Celery/Native).

### Step 9: Password Reset Confirm (Execution)

- **Goal:** Finalize password change transactionally.
- **Actions:**
  - **Async (`apis/password_views/async_views.py`)**:
    - Fast verification of Token/OTP.
    - `user.aset_password()` (native async).
  - **Sync (`apis/password_views/sync_views.py`)**:
    - Standard DRF `PasswordResetConfirmView`.
  - **Security:** Invalidate all existing sessions/tokens upon success.

### Step 10: Final Hardening & Integration

- **Goal:** "Industrial Enterprise Grade" polish.
- **Actions:**
  - **URLs:** Wire up `apps/authentication/urls.py` with `v1` (DRF) and `v2` (Ninja) paths.
  - **Logging:** Audit all Auth endpoints with `application_logger` (Entry/Exit/Fail).
  - **Exceptions:** Ensure `apps/common/exceptions.py` catches `OTPFailed`, `UserNotFound`, etc., and renders standardized JSON errors for both engines.
  - **Docs:** Auto-generate Swagger for both V1 and V2 to verify schema correctness.

---

## 🛠️ DEPENDENCIES (MAPPED FROM LEGACY)

- **Email:** `apps/common/utils.py` / `userauths.tasks` -> `apps/common/tasks.py`.
- **SMS:** `apps/common/utils.py` (Twilio/Provider integration).
- **Redis:** `utilities.django_redis` -> `apps/common/providers/redis_provider.py`.
