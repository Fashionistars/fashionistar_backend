# AUTHENTICATION IMPLEMENTATION ROADMAP

## Complete Study & 10-Step Enterprise-Grade Implementation Plan

### Version 2.0 (Execution Phase)

### Date: Feb 2026

---

## EXECUTIVE SUMMARY

This document represents a **comprehensive study and analysis** of the existing authentication system, combined with a **10-step implementation roadmap** that bridges the `userauths` legacy application with the new `apps/authentication` and `apps/common` modules designed for Django 6.0+ async-first architecture.

**Current State Analysis:**

- Legacy `userauths` uses DRF, Celery tasks, Redis OTP encryption (Fernet), and atomic transactions.
- New `apps/authentication` has modern async services (`auth_service.py`, `otp_service.py`) with support for Dual-Engine (Sync+Async).
- Unified `UnifiedUser` model merges legacy Profile data via `apps/common`.

**Target State:**

- **Industrial-Grade Separation:** Strict wall between Sync (DRF) and Async (Ninja) logic.
- **Dual-Engine:** Parallel implementation for all 4 key flows (Register, OTP, Login, Password).
- **Security:** Fernet OTP encryption, Redis TTL, atomic transactions, and IP-based throttling.

---

## PART A: EXISTING DESIGN ANALYSIS (The "Old" `userauths`)

### A.1. View Layer Pattern (DRF Generics)

Legacy `RegisterViewCelery` uses `@transaction.atomic` to wrap user creation, OTP generation, and Celery dispatch.
**Insight:** We must preserve this atomicity. If Redis fails or Email fails, the User DB record must rollback.

### A.2. OTP Flow Pattern

Legacy uses a direct Redis key pattern: `otp_data:{user_id}:{encrypted_otp}`.
**Insight:** We will upgrade this to **Purpose-Scoped Keys** (`otp:{user_id}:{purpose}:{encrypted_otp}`) to prevent OTP reuse across features (e.g., using a signup OTP for password reset).

### A.3. Encryption Pattern

Legacy uses `encrypt_otp` (Fernet) from `utilities`.
**Insight:** We will use `apps/common/utils.py` which standardizes this with the same `SECRET_KEY`.

---

## PART B: 10-STEP IMPLEMENTATION ROADMAP

### **SEGMENT 1: REGISTRATION (SYNC & ASYNC)**

#### **STEP 1: Implement Registration Service (Both Sync & Async)**

**Location:** `apps/authentication/services/registration_service.py`
**Actions:**

- **Sync Logic (`register_sync`):**
  - Atomic Transaction.
  - `CustomUserManager.create_user()`.
  - `OTPService.generate_otp_sync()`.
  - `EmailManager.send_mail()` / `SMSManager.send_sms()`.
- **Async Logic (`register_async`):**
  - Async Atomic Transaction.
  - `CustomUserManager.acreate_user()` (Native Async).
  - `OTPService.generate_otp_async()`.
  - `EmailManager.asend_mail()` (Native Async).

#### **STEP 2: Implement Registration Serializer & Validation**

**Location:** `apps/authentication/serializers.py`
**Actions:**

- Extend `UserRegistrationSerializer`.
- **Validation Rules:**
  - `email` XOR `phone` (One required, not both).
  - `password` strength & matching.
  - `role` allowed choices.
  - **Uniqueness Check:** Pre-check `UnifiedUser.objects.filter(...)` before saving.

#### **STEP 3: Implement Registration Views (Sync & Async)**

**Location:** `apis/auth/sync_views.py` & `async_views.py`
**Actions:**

- **Sync (DRF):** `RegisterView(CreateAPIView)`. Uses `BurstRateThrottle`.
- **Async (Ninja/ADRF):** `AsyncRegisterView`. Uses non-blocking `await` calls.
- **Response:** Standardized JSON (`{success: true, message: "...", data: ...}`).

---

### **SEGMENT 2: OTP VERIFICATION & RESEND**

#### **STEP 4: Implement OTP Verification Service**

**Location:** `apps/authentication/services/otp_service.py`
**Actions:**

- **Redis Pattern:** Use `scan_iter` to find keys `otp:{user_id}:{purpose}:*`.
- **Decryption:** Retrieve -> Decrypt -> Compare.
- **Cleanup:** Delete key immediately upon usage (One-Time Use).
- **Activation:** Set `is_active=True`, `is_verified=True`.
- **Token Issue:** Generate JWT (Refresh/Access) immediately upon verification.

#### **STEP 5: Verify & Resend Endpoints**

**Location:** `apis/auth/sync_views.py` & `async_views.py`
**Actions:**

- **Sync:** `VerifyOTPView` & `ResendOTPView`.
- **Async:** `AsyncVerifyOTPView` & `AsyncResendOTPView`.
- **Resend Logic:** Invalidate _old_ OTP -> Generate New -> Dispatch.

---

### **SEGMENT 3: LOGIN (SYNC & ASYNC)**

#### **STEP 6: Implement Login Service (Dual-Engine)**

**Location:** `apps/authentication/services/auth_service.py`
**Actions:**

- **Logic:**
  - Find User (Email/Phone).
  - Check Password (`check_password`).
  - Check `is_active`/`is_verified`.
  - Update `last_login`.
  - Generate Tokens.
- **Audit:** Log IP, User-Agent, and Timestamp.

#### **STEP 7: Implement Login Serializers & Views**

**Location:** `apis/auth/sync_views.py` & `async_views.py`
**Actions:**

- **Sync:** `LoginView(GenericAPIView)`.
- **Async:** `AsyncLoginView` (Native Async).
- **Security:** Strict output serialization (no password leaking).

#### **STEP 8: Google Auth Integration**

**Location:** `apps/authentication/services/google_service.py`
**Actions:**

- **Verify:** Validate Google ID Token with Google Servers.
- **Get/Create:** Find user by email OR create new instance.
- **Auto-Verify:** Google users are `is_verified=True` by default.
- **Issue:** JWT Tokens.

---

### **SEGMENT 4: PASSWORD MANAGEMENT**

#### **STEP 9: Password Reset Request (Dispatch)**

**Location:** `apps/authentication/services/password_service.py`
**Actions:**

- **Email Flow:** Generate Token (`default_token_generator`) -> Email Link.
- **Phone Flow:** Generate OTP -> SMS.
- **Security:** Generic response ("If account exists...") to prevent enumeration.

#### **STEP 10: Password Reset Confirm (Execution)**

**Location:** `apis/password/sync_views.py` & `async_views.py`
**Actions:**

- **Verify:** Check Token/OTP validity in Redis.
- **Action:** `user.set_password(new_passwd)`.
- **Cleanup:** Delete Token/OTP.
- **Hardening:** Invalidate existing sessions if possible.

---

## PART C: DEPENDENCY MAPPING

| Component      | Legacy Source                     | New Destination                                             |
| -------------- | --------------------------------- | ----------------------------------------------------------- |
| **User Model** | `userauths.models.User`           | `apps/authentication.models.UnifiedUser`                    |
| **Email**      | `userauths.tasks.send_email_task` | `apps/common.managers.email.EmailManager`                   |
| **SMS**        | `userauths.tasks.send_sms_task`   | `apps/common.managers.sms.SMSManager`                       |
| **Redis**      | `utilities.django_redis`          | `apps/common.providers.redis_provider`                      |
| **Encryption** | `utilities.encrypt_otp`           | `apps/common.utils.encrypt_otp`                             |
| **Views**      | `RegisterViewCelery`              | `services.registration_service` + `apis/auth/sync_views.py` |

## PART D: TECHNICAL REQUIREMENTS

1.  **Strict Separation:** `sync_views.py` MUST NOT contain `async def`. `async_views.py` MUST NOT contain blocking calls.
2.  **Robust Error Handling:** Every `try` block must catch `ValidationError` and generic `Exception` with distinct logging.
3.  **Logging:** Every entry point and exit point must be logged using `application_logger`.
