# SUPREME BACKEND_AUTH.MD - Authentication & Authorization Architectural Blueprint
**Version:** 2.0 (Enterprise Edition)  
**Status:** Approved for Implementation  
**Architecture:** Modular Monolith (Domain-Driven Design)  
**Framework:** Django 6.0 Ready (Async-First)

---

## 1. Executive Summary & Core Philosophy

This document dictates the complete refactoring of the existing `userauths` application into a decoupled, high-performance Identity System located at `apps/authentication`. This is an "Industrial-Grade" architectural blueprint designed for scalability, security, and maintainability.

### 1.1. The "Parallel Migration" Protocol (Safety First)
To ensure **Zero Data Loss** and **Zero Downtime**, we strictly adhere to the following protocol:
1.  **NO DELETION**: We do NOT delete the existing `userauths` app or `Profile` model yet.
2.  **PARALLEL BUILD**: We will build `apps/authentication` and `apps/common` alongside the old app.
3.  **COPY & REFACTOR**: Logic is copied line-by-line, refactored for strict typing and async patterns.
4.  **DATA MIGRATION**: A robust script will migrate data from `Userauths.Profile` -> `Authentication.User`.
5.  **VERIFICATION**: Only after 100% test coverage and data verification will the old app be deprecated.

### 1.2. Key Architectural Decisions
*   **Dissolution of Profile**: The OneToOne `Profile` model is an anti-pattern for high-performance lookups. It will be merged into the `User` model to reduce DB joins.
*   **Separation of Concerns**: `wallet_balance` is **REMOVED** from Authentication. It belongs in a future `apps/finance` module.
*   **Microservice-Ready Relations**: No direct model imports between apps. Use String References (e.g., `ForeignKey("vendor.Vendor")`) to prevent circular imports and allow future splitting.
*   **Hybrid Auth Strategy**: Support for Email, Phone, and Google (via ID Token server-side verification).
*   **Async-First**: All I/O bound operations (DB, External APIs, Email) must be asynchronous.
*   **Data Retention**: `SoftDeleteModel` for recovery and audit; `HardDelete` for GDPR compliance (restricted to Admins).

---

## 2. Directory Structure (The New Standard)

We are restructuring the root to use an `apps/` directory to keep the project clean and domain-focused.

```text
root/
├── apps/
│   ├── common/                  # [THE FOUNDATION] Shared Utilities
│   │   ├── __init__.py
│   │   ├── models.py            # Base Models (TimeStamped, SoftDelete)
│   │   ├── permissions.py       # Async Permissions (IsVendor, IsStaff)
│   │   ├── renderers.py         # Standardized JSON Response Formats
│   │   ├── exceptions.py        # Global Exception Handler (JSON formatted)
│   │   └── utils.py             # Shared Helpers (Redis wrappers, Encryption)
│   │
│   └── authentication/          # [THE IDENTITY MODULE]
│       ├── __init__.py
│       ├── apps.py              # AppConfig (Verbose Name: "Identity Access Management")
│       ├── urls.py              # API Routes: /api/v1/auth/...
│       ├── admin.py             # Custom Admin with Audit Logs & Hard Delete Actions
│       ├── models.py            # NEW Merged User Model
│       ├── permissions.py       # Auth-specific permissions
│       ├── services/            # [WRITE LAYER - Pure Business Logic]
│       │   ├── __init__.py
│       │   ├── auth_service.py  # Login, Register, Logout (Async)
│       │   ├── google_service.py# Hybrid Google Token Verification
│       │   └── otp_service.py   # Redis OTP Logic (Encryption/Decryption)
│       ├── selectors/           # [READ LAYER - Optimized Queries]
│       │   ├── __init__.py
│       │   └── user_selector.py # "Get Profile", "Get User Stats"
│       ├── apis/                # [INTERFACE LAYER - Thin Views]
│       │   ├── __init__.py
│       │   ├── auth_views.py    # Login/Register endpoints
│       │   ├── password_views.py# Reset/Change Password
│       ├── types/               # [VALIDATION LAYER]
│       │   └── auth_schemas.py  # Pydantic Schemas (Strict Input Validation)
│       ├── cores/               # [ADVANCED PROCESSING]
│       │   ├── __init__.py
│       │   ├── api_ingress.py   # Input sanitization
│       │   └── orchestrator.py  # Workflow coordination
│       └── tests/
│           ├── test_services.py
│           └── test_flows.py
```

---

## 3. The apps/common Foundation (Reusability)

We must establish the base classes in `apps/common/models.py` before building Auth. 

### 3.1. Universal Models (`apps/common/models.py`)

#### TimeStampedModel
An abstract base class that provides self-updating `created_at` and `updated_at` fields.

#### SoftDeleteModel & Hard Delete Logic
We implement a rigorous data retention policy. Records are hidden by default but can be permanently removed if necessary.

```python
from django.db import models
from django.utils import timezone

class SoftDeleteModel(models.Model):
    """
    Abstract base class that prevents physical deletion of records.
    Instead, it marks them as deleted for Audit/Recovery purposes.
    
    Attributes:
        is_deleted (bool): Restoration flag.
        deleted_at (datetime): When the record was soft-deleted.
    """
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        """Marks the record as deleted and timestamps it."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        """Restores a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.save()
        
    def hard_delete(self):
        """
        PERMANENTLY deletes the record from the database.
        WARNING: This cannot be undone. 
        Protected method: Should only be called by Superusers/Admins.
        """
        # Logic to delete associated media files (Cloudinary) from here if needed
        super().delete()
```

### 3.2. Global Permissions (`apps/common/permissions.py`)
Implement granular, async-compatible permissions:
*   `IsVendor`, `IsClient`, `IsStaff` (Support/Reviewer), `IsAdmin`, `IsOwner`.
*   **Logic**: Permissions should check `request.user.role` efficiently (cached).

---

## 4. The apps/authentication Data Model

### 4.1. The Great Merger (`models.py`)
We are dissolving the `Profile` model and merging it into `User`.
**Crucial**: All fields must be properly indexed for performance.

```python
# apps/authentication/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.common.models import TimeStampedModel, SoftDeleteModel
from phonenumber_field.modelfields import PhoneNumberField

class User(AbstractUser, TimeStampedModel, SoftDeleteModel):
    """
    The Central Identity Entity.
    
    Merged Fields from legacy Profile:
    - bio, phone, avatar (was image), country, city, state, address.
    - is_verified (moved from profile).
    
    New Architecture Fields:
    - auth_provider: Tracks if user signed up via Email, Phone, or Google.
    - role: RBAC (Role Based Access Control).
    """
    
    # Auth Providers
    PROVIDER_EMAIL = "email"
    PROVIDER_PHONE = "phone"
    PROVIDER_GOOGLE = "google"
    
    PROVIDER_CHOICES = [
        (PROVIDER_EMAIL, "Email"),
        (PROVIDER_PHONE, "Phone"),
        (PROVIDER_GOOGLE, "Google"),
    ]

    # Roles
    ROLE_VENDOR = "vendor"
    ROLE_CLIENT = "client"
    ROLE_STAFF = "staff" # Support/Reviewers
    ROLE_ADMIN = "admin"
    
    ROLE_CHOICES = [
        (ROLE_VENDOR, "Vendor"),
        (ROLE_CLIENT, "Client"),
        (ROLE_STAFF, "Staff"),
        (ROLE_ADMIN, "Admin"),
    ]

    # Identification
    username = None # Removed to use email as primary
    email = models.EmailField(unique=True, null=True, db_index=True)
    phone = PhoneNumberField(unique=True, null=True, db_index=True)
    
    # Profile Data (Merged)
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", default="default.jpg")
    bio = models.TextField(blank=True)
    
    # Location (Essential for Logistics)
    country = models.CharField(max_length=100, blank=True, db_index=True)
    state = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    
    # System Fields
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CLIENT, db_index=True)
    auth_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_EMAIL)
    is_verified = models.BooleanField(default=False, db_index=True)
    
    # Verification Codes (QR/PID from old model)
    pid = models.CharField(max_length=50, unique=True, null=True) # ShortUUID

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone']

    class Meta:
        indexes = [
            models.Index(fields=['email', 'role']),
            models.Index(fields=['phone', 'role']),
        ]

    def __str__(self):
        return self.email if self.email else str(self.phone)
```

---

## 5. Industrial-Grade Logic Implementation

### 5.1. Pydantic Schemas (`types/auth_schemas.py`)
We use Pydantic to strictly validate inputs before they reach our Service layer.

```python
from pydantic import BaseModel, EmailStr, validator

class GoogleAuthSchema(BaseModel):
    id_token: str
    
    @validator('id_token')
    def validate_token(cls, v):
        if not v or len(v) < 50:
            raise ValueError("Invalid Google ID Token")
        return v

class LoginSchema(BaseModel):
    email_or_phone: str
    password: str
```

### 5.2. Service Layer: The "Brain" (`services/`)

#### A. `otp_service.py` (Redis + Encryption)
*   **Storage**: Use Redis with key `otp:{user_id}:{purpose}`.
*   **TTL**: 300 seconds (5 minutes).
*   **Encryption**: Securely encrypt OTPs before storing using `apps.common.utils` crypto helpers.
*   **Logic**: Generate 6-digit numeric code using `secrets.randbelow`.

#### B. `google_service.py` (Hybrid Strategy)
This handles the **Server-Side Verification** of Google ID Tokens.

```python
# apps/authentication/services/google_service.py

from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings
from apps.authentication.models import User
import logging

logger = logging.getLogger("application")

class GoogleAuthService:
    """
    Handles Server-Side Verification of Google ID Tokens sent from the Client.
    """
    
    @staticmethod
    async def verify_and_login(token: str):
        """
        Verifies the ID token with Google's servers.
        
        Args:
            token (str): The JWT ID Token from the client.
            
        Returns:
            User: The authenticated user instance.
            
        Raises:
            ValueError: If token is invalid/expired.
        """
        try:
            # Async verification logic
            id_info = id_token.verify_oauth2_token(
                token, requests.Request(), settings.GOOGLE_CLIENT_ID
            )
            
            email = id_info['email']
            
            # Logic: Find or Create
            try:
                user = await User.objects.aget(email=email)
            except User.DoesNotExist:
                # Create new user via Google
                user = await User.objects.acreate(
                    email=email,
                    auth_provider=User.PROVIDER_GOOGLE,
                    is_verified=True, # Trusted provider
                    role=User.ROLE_CLIENT
                )
                logger.info(f"New User Registered via Google: {email}")
                
            return user
            
        except ValueError as e:
            logger.error(f"Google Auth Failed: {str(e)}")
            raise Exception("Invalid Google Token")
```

#### C. `auth_service.py`
*   Handles `login`, `register`, `logout`.
*   **Rate Limiting**: "5 strikes = 15 min ban". Check Redis key `login_fail_attempts:{ip}`.
*   **Audit Logging**: Capture `HTTP_USER_AGENT` and IP Address.

---

## 6. Security, Audit, and Compliance

### 6.1. Audit Logging (`django-auditlog`)
*   **Requirement**: Track all changes to `User` and `Vendor` models.
*   **Fields**: Who changed it, What changed (Old -> New), When, IP Address.
*   **Implementation**: Register models in `admin.py` or `apps.py` (signals).

### 6.2. Rate Limiting (Redis)
*   Implement a "5 Strikes" Rule.
*   **On Login Attempt**: Check Redis key `login_fail:{ip_address}`.
*   **If Value >= 5**: Raise `PermissionDenied("Too many attempts. Try again in 15 minutes.")`.
*   **On Failure**: Increment key, set expiry 15 mins.
*   **On Success**: Delete key.

### 6.3. Hard Delete (Protected)
We create a custom Admin Action for GDPR compliance.
*   **Access**: `IsSuperUser` only.
*   **Process**:
    1.  Delete associated Cloudinary assets (Async celery task).
    2.  Call `user.hard_delete()`.
    3.  Log the action in Audit Log.

### 6.4. Session Management
*   Configure Django to use Redis for caching user sessions.
*   **Settings**: `SESSION_ENGINE = "django.contrib.sessions.backends.cache"`.
*   **Cache Alias**: "default" (pointing to Redis).

---

## 7. Migration Strategy (The Transfer)

Management Command: `apps/authentication/management/commands/migrate_legacy_users.py`

**Logic Flow:**
1.  Init Logger.
2.  Iterate `Userauths.User.objects.all()`.
3.  Fetch related `Userauths.Profile` (handle `DoesNotExist`).
4.  **Transform**:
    *   `NewUser.bio` = `OldProfile.bio`
    *   `NewUser.phone` = `OldProfile.phone`
    *   `NewUser.auth_provider` = "email" (default if not known)
5.  **Save** to `apps.authentication.models.User`.
6.  **Verify**: Compare counts.

---

## 8. Coding & Documentation Standards

1.  **Strict Typing**: Every function signature MUST have type hints.
    *   `def my_func(user: User, data: dict) -> bool:`
2.  **Robust Docstrings**: Google-style docstrings are MANDATORY.
    *   **Args**: List arguments and their types.
    *   **Returns**: Describe the return value.
    *   **Raises**: List possible exceptions.
3.  **Error Handling**:
    *   Wrap DB calls in `try/except`.
    *   Return distinct, human-readable error messages for UI.
4.  **Logging**:
    *   Log distinct events (Login Success, Login Fail, Register).
    *   Use `logger.info`, `logger.warning`, `logger.error` appropriately.

---

**Approved Recommendations Config:**
*   **Hybrid OAuth2**: YES (Implemented).
*   **Biometric Auth**: YES (WebAuthn prepared in architecture).
*   **Rate Limiting**: YES (Redis).
*   **Session Management**: YES (Redis).
*   **Audit Trail**: YES (django-auditlog).
