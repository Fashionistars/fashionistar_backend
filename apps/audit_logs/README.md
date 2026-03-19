# `apps/audit_logs` — Enterprise Audit Event Logging

> **Version** 2026-03-19 · **Django** 6.0.2 · **Fashionistar Engineering**
>
> 7-year compliance-grade audit trail for financial, security, AI measurement, and business operations. Non-blocking, immutable, searchable, with fraud detection insights.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Quick Start](#quick-start)
3. [Core Concepts](#core-concepts)
4. [Models & Fields](#models--fields)
5. [AuditService API](#auditservice-api)
6. [Event Types Reference](#event-types-reference)
7. [Django Admin Integration](#django-admin-integration)
8. [Middleware: Auto-Context Capture](#middleware-auto-context-capture)
9. [Admin Actions Audit (AuditedModelAdmin)](#admin-actions-audit-auditedmodeladmin)
10. [Step-by-Step Integration Guide for New Apps](#step-by-step-integration-guide-for-new-apps)
11. [Advanced Usage & Querying](#advanced-usage--querying)
12. [Security & Compliance](#security--compliance)
13. [File Structure](#file-structure)
14. [Database Schema & Indexes](#database-schema--indexes)
15. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
HTTP Request / Admin Action / Celery Task
        │
        ▼
AuditService.log(...)  ◀─ Called from views, services, middleware (any thread)
(apps/audit_logs/services/audit.py)
        │
        ├─► Resolve actor, IP, user-agent, device info
        ├─► UA parsing (browser/OS family)
        └─► Dispatch to Celery task (async, never blocks)
                │
                ▼
        write_audit_event.apply_async()  ◀─ Enqueued to Redis immediately
        (apps/audit_logs/tasks.py)
                │
                ├─► Try Celery worker write
                ├─► Retry up to 2 times on transient DB errors
                └─► log WARNING on persistent failure (never crash)
                        │
                        ▼
                AuditEventLog.objects.create()  ◀─ Immutable DB row
                (apps/audit_logs/models.py)
                        │
                        └─► Indexed for fast queries, 7-year retention
```

### Design Principles

| Principle | Implementation |
|---|---|
| **Non-Blocking** | Direct `apply_async()` dispatch — HTTP request completes immediately |
| **Fault-Tolerant** | Celery retry + sync fallback — events NEVER lost or silently dropped |
| **Immutable** | No update/delete in application code; admin read-only; database-enforced |
| **Tamper-Proof** | Created-at immutable; no delete permission; archived for 7 years |
| **Enriched Context** | IP, device, browser, OS, actor snapshot, before/after diffs, correlation ID |
| **Compliant** | Financial audit trails (GDPR, PCI-DSS, SOC2 ready) |

---

## Quick Start

### Installation

1. **Add to `INSTALLED_APPS`** (in `backend/config/base.py`):
```python
INSTALLED_APPS = [
    ...
    'apps.audit_logs',
    ...
]
```

2. **Add middleware** (in `backend/config/base.py`):
```python
MIDDLEWARE = [
    ...
    'apps.audit_logs.middleware.AuditContextMiddleware',
    ...
]
```

3. **Run migrations**:
```bash
python manage.py migrate
```

### 1. Log a Simple Event

```python
from apps.audit_logs.services.audit import AuditService
from apps.audit_logs.models import EventType, EventCategory

# Minimal — context auto-filled by middleware
AuditService.log(
    event_type=EventType.LOGIN_SUCCESS,
    event_category=EventCategory.AUTHENTICATION,
    action="User logged in successfully",
    request=request,  # optional — auto-extracts IP, UA, method, path
)
# ✅ Non-blocking — returns immediately
```

### 2. Log with Full Context (Before/After Diffs)

```python
AuditService.log(
    event_type=EventType.ACCOUNT_UPDATED,
    event_category=EventCategory.ACCOUNT,
    action="Profile bio updated via settings page",
    severity="info",
    request=request,
    resource_type="UnifiedUser",
    resource_id=str(user.pk),
    old_values={"bio": "Old bio text"},
    new_values={"bio": "New bio text"},
    metadata={"source": "profile_settings"},
    is_compliance=True,  # 7-year retention
)
```

### 3. Log Payment Transactions (Financial)

```python
AuditService.log(
    event_type=EventType.PAYMENT_SUCCESS,
    event_category=EventCategory.PAYMENT,
    action=f"Payment of ₦{amount:,.2f} completed via Paystack",
    severity="info",
    request=request,
    resource_type="Order",
    resource_id=str(order.pk),
    metadata={
        "payment_ref": payment_ref,
        "gateway": "paystack",
        "amount_kobo": str(int(amount * 100)),
        "currency": "NGN",
        "receipt_url": receipt_url,
    },
    is_compliance=True,  # Flagged for compliance audit
)
```

### 4. Log AI Measurement Events

```python
AuditService.log(
    event_type=EventType.AI_ANALYSIS_COMPLETED,
    event_category=EventCategory.MEASUREMENT,
    action="Body measurement analysis completed — AI v2.1",
    severity="info" if confidence > 0.85 else "warning",
    resource_type="Measurement",
    resource_id=str(measurement.pk),
    metadata={
        "model_version": "v2.1",
        "confidence_score": f"{confidence:.4f}",
        "processing_time_ms": int(elapsed_ms),
        "measurements": {
            "chest": str(measurements['chest']),
            "waist": str(measurements['waist']),
        },
    },
    is_compliance=False,  # Not financial
)
```

---

## Core Concepts

### AuditEventLog Model

Immutable, high-value business event record. **Never updated or deleted** after creation.

**Example rows:**

```
┌─────────────────────────────────────────────────────────────┐
│ id: 550e8400-e29b... | event_type: LOGIN_SUCCESS             │
│ actor_email: alice@example.com                               │
│ ip_address: 192.168.1.100                                    │
│ device_type: mobile | browser_family: Chrome                 │
│ severity: info | created_at: 2026-03-19T14:23:45.123Z        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ id: 660e8400-e29b... | event_type: PAYMENT_SUCCESS           │
│ actor_email: vendor@shop.com                                 │
│ resource_type: Order | resource_id: order_7890               │
│ severity: info | is_compliance: true | created_at: 2026-03-19T14:22:11.500Z │
│ metadata: {                                                   │
│   "payment_ref": "PSK_12345678",                              │
│   "amount_kobo": "500000",                                    │
│   "gateway": "paystack"                                       │
│ }                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Event Types & Categories

**15 Categories** with 51+ Event Types for comprehensive business logging:

| Category | Examples | Use Case |
|---|---|---|
| **Authentication** | LOGIN_SUCCESS, LOGIN_FAILED, LOGOUT, TOKEN_REFRESHED | User sessions |
| **Account** | ACCOUNT_CREATED, ACCOUNT_UPDATED, ACCOUNT_SOFT_DELETED, AVATAR_UPLOADED | User profile changes |
| **Security** | PASSWORD_CHANGED, PASSWORD_RESET_DONE, MFA_ENABLED, SUSPICIOUS_ACTIVITY | Fraud + access control |
| **Admin** | ADMIN_ACTION, ADMIN_BULK_DELETE, ADMIN_BULK_IMPORT | Staff auditing |
| **Payment** | PAYMENT_SUCCESS, PAYMENT_FAILED, REFUND_INITIATED, DISPUTE_RESOLVED | Financial compliance |
| **Order** | ORDER_CREATED, ORDER_UPDATED, ORDER_FULFILLED, ORDER_RETURNED | E-commerce audit |
| **Cart** | CART_UPDATED, CHECKOUT_STARTED, CHECKOUT_COMPLETED | Checkout funnel |
| **Measurement** | MEASUREMENT_CREATED, AI_ANALYSIS_COMPLETED, AI_ANALYSIS_FAILED | AI operations |
| **Compliance** | (metadata-driven) | Regulatory requirements |

---

## Models & Fields

### AuditEventLog

```python
class AuditEventLog(models.Model):
    # Primary Key
    id = UUIDField(primary_key=True, default=uuid7)  # Time-sortable

    # Event Classification
    event_type = CharField(max_length=60, choices=EventType.choices, indexed)
    event_category = CharField(max_length=60, choices=EventCategory.choices, indexed)
    severity = CharField(choices=[debug, info, warning, error, critical], indexed)
    action = TextField()  # Human-readable: "User logged in from Chrome mobile"

    # Actor (Who)
    actor = ForeignKey(UnifiedUser, null=True, on_delete=models.SET_NULL)  # Nullable for system events
    actor_email = EmailField(null=True, indexed)  # Snapshot — survives user hard-delete

    # Request Context
    ip_address = GenericIPAddressField(null=True, indexed)
    user_agent = TextField(null=True)  # Full UA string
    device_type = CharField(null=True)  # desktop / mobile / tablet / api / unknown
    browser_family = CharField(null=True)  # Chrome / Firefox / Safari
    os_family = CharField(null=True)  # Windows / macOS / iOS / Android
    country = CharField(null=True, indexed)  # GeoIP-resolved country code

    # Distributed Tracing
    correlation_id = CharField(max_length=64, null=True, indexed)  # X-Request-ID cross-correlation

    # Resource Affected
    resource_type = CharField(max_length=100, null=True, indexed)  # Model class name
    resource_id = CharField(max_length=255, null=True, indexed)  # Resource PK

    # HTTP Context
    request_method = CharField(max_length=10, null=True)  # GET / POST / PUT / DELETE
    request_path = CharField(max_length=500, null=True)  # /api/v1/orders/
    response_status = PositiveSmallIntegerField(null=True)  # 200 / 400 / 500
    duration_ms = FloatField(null=True)  # Handler execution time

    # Diff / Forensic Restore
    old_values = JSONField(null=True)  # Before-state (sensitive fields redacted)
    new_values = JSONField(null=True)  # After-state
    metadata = JSONField(null=True)  # Arbitrary key-value context

    # Error / Failure
    error_message = TextField(null=True)  # If event represents failure

    # Compliance & Retention
    is_compliance = BooleanField(default=False, indexed)  # Flag for audit review
    retention_days = PositiveIntegerField(default=2555)  # 7 years = 2555 days

    # Immutable Timestamp
    created_at = DateTimeField(auto_now_add=True, indexed)

    class Meta:
        ordering = ["-created_at"]
        indexes = [11 composite indexes for common queries]
```

### All Supported Fields

| Field | Type | Indexed | Null | Notes |
|---|---|---|---|---|
| `id` | UUID7 | ✅ | No | Time-sortable PK |
| `event_type` | CharField | ✅ | No | EventType enum |
| `event_category` | CharField | ✅ | No | EventCategory enum |
| `severity` | CharField | ✅ | No | debug/info/warning/error/critical |
| `action` | TextField | No | No | Human description of event |
| `actor` | FK → UnifiedUser | Yes (ind) | ✅ | Who triggered event |
| `actor_email` | EmailField | ✅ | ✅ | Email snapshot (survives deletion) |
| `ip_address` | GenericIPAddressField | ✅ | ✅ | Client IP (X-Forwarded-For aware) |
| `user_agent` | TextField | No | ✅ | Full UA string |
| `device_type` | CharField | No | ✅ | desktop/mobile/tablet/api |
| `browser_family` | CharField | No | ✅ | Chrome/Firefox/Safari/…|
| `os_family` | CharField | No | ✅ | Windows/macOS/iOS/Android/…|
| `country` | CharField | ✅ | ✅ | GeoIP country code |
| `correlation_id` | CharField | ✅ | ✅ | X-Request-ID for tracing |
| `resource_type` | CharField | ✅ | ✅ | Affected model name |
| `resource_id` | CharField | ✅ | ✅ | Affected object PK |
| `request_method` | CharField | No | ✅ | GET/POST/PUT/PATCH/DELETE |
| `request_path` | CharField | No | ✅ | URL path |
| `response_status` | PositiveSmallIntegerField | No | ✅ | HTTP status code |
| `duration_ms` | FloatField | No | ✅ | Handler time in ms |
| `old_values` | JSONField | No | ✅ | Before-state (redacted) |
| `new_values` | JSONField | No | ✅ | After-state |
| `metadata` | JSONField | No | ✅ | Arbitrary context |
| `error_message` | TextField | No | ✅ | Failure reason |
| `is_compliance` | BooleanField | ✅ | No | 7-year retention flag |
| `retention_days` | PositiveIntegerField | No | No | Retention period |
| `created_at` | DateTimeField | ✅ | No | Immutable timestamp |

---

## AuditService API

**File:** `apps/audit_logs/services/audit.py`

### Method Signature

```python
@classmethod
def AuditService.log(
    *,  # Keyword-only arguments
    # Event Classification (required)
    event_type: str,
    event_category: str,
    action: str,
    severity: str = "info",  # debug / info / warning / error / critical

    # Actor (optional — auto-resolved if not provided)
    actor = None,  # UnifiedUser instance
    actor_email: str | None = None,

    # Request Context (optional — auto-filled by middleware if None)
    request = None,  # Django HttpRequest
    ip_address: str | None = None,
    user_agent: str | None = None,
    device_type: str | None = None,
    browser_family: str | None = None,
    os_family: str | None = None,
    request_method: str | None = None,
    request_path: str | None = None,
    response_status: int | None = None,
    duration_ms: float | None = None,

    # Resource Affected
    resource_type: str | None = None,  # Model class name (e.g., 'Product')
    resource_id: str | None = None,    # Resource PK (e.g., 'prod_12345')

    # Diff / Context
    old_values: dict | None = None,    # Before-state snapshot
    new_values: dict | None = None,    # After-state snapshot
    metadata: dict | None = None,      # Arbitrary key-value context
    error_message: str | None = None,  # Error reason if failure

    # Compliance & Retention
    is_compliance: bool = False,        # Flag for compliance audit
    retention_days: int = 2555,         # 7 years = 2555 days
) -> None:  # Returns immediately — always succeeds (never raises)
```

### Dispatch Mechanism

**Key behavior: `apply_async()` is called DIRECTLY, NOT inside `transaction.on_commit()`**

```python
# Why? Three reasons:
# 1. Events are enqueued to Redis immediately, regardless of TX commit/rollback
# 2. Failed-request audit logs (e.g., validation errors in atomic()) are never dropped
# 3. Celery worker writes in its own connection, so no lock contention

write_audit_event.apply_async(kwargs={"payload": ...}, retry=False)
#              ↑ Enqueued NOW, even if calling TX rolls back
#              ↑ Worker retries up to 2x on transient errors
#              ↑ Logged as WARNING on persistent failure (never crashes)

# If Celery broker is down:
#   → Sync fallback: writes directly to DB
#   → Events NEVER silently dropped
```

---

## Event Types Reference

### Full Event Catalog (51 types across 15 categories)

**Authentication (8 types)**
```python
LOGIN_SUCCESS              # Successful login
LOGIN_FAILED               # Failed login attempt
LOGIN_BLOCKED              # Login blocked (rate limit / suspicious)
LOGOUT                     # User logged out
TOKEN_REFRESHED            # JWT refresh token used
GOOGLE_LOGIN               # Google OAuth login
REGISTER_SUCCESS           # Registration success
REGISTER_FAILED            # Registration failure (email exists, weak password, etc.)
```

**Account & Profile (8 types)**
```python
ACCOUNT_CREATED            # New account created
ACCOUNT_UPDATED            # Profile updated (bio, name, etc.)
ACCOUNT_SOFT_DELETED       # Account soft-deleted (recoverable)
ACCOUNT_RESTORED           # Soft-deleted account restored
ACCOUNT_HARD_DELETED       # Permanent account deletion (GDPR)
EMAIL_VERIFIED             # Email verification completed
PHONE_VERIFIED             # Phone verification completed
AVATAR_UPLOADED            # Avatar uploaded to Cloudinary
```

**Security (8 types)**
```python
PASSWORD_CHANGED           # User changed password
PASSWORD_RESET_REQUEST     # Password reset OTP sent
PASSWORD_RESET_DONE        # Password reset completed
MFA_ENABLED                # Multi-factor authentication enabled
MFA_DISABLED               # MFA disabled
SUSPICIOUS_ACTIVITY        # Anomalous behavior detected
IP_BLOCKED                 # IP address blocked
FAILED_LOGINS_EXCEEDED     # Too many failed login attempts
```

**Admin Actions (5 types)**
```python
ADMIN_ACTION               # Single admin save/delete/edit
ADMIN_BULK_EXPORT          # CSV/XLSX export from admin
ADMIN_BULK_IMPORT          # Data import via CSV/XLSX
ADMIN_BULK_DELETE          # Bulk delete from changelist
SETTINGS_CHANGED           # System settings changed
```

**Data Operations (3 types)**
```python
DATA_VIEWED                # Sensitive data viewed
DATA_EXPORTED              # Data exported (GDPR subject access request)
SENSITIVE_DATA_ACCESS      # PII / financial data accessed
```

**E-Commerce: Orders (5 types)**
```python
ORDER_CREATED              # Order created
ORDER_UPDATED              # Order status updated
ORDER_CANCELLED            # Order cancelled
ORDER_FULFILLED            # Order shipped/fulfilled
ORDER_RETURNED             # Order returned
```

**E-Commerce: Payments (7 types)** — *Financial Compliance Critical*
```python
PAYMENT_INITIATED          # Payment started
PAYMENT_SUCCESS            # Payment successful (PCI-DSS level)
PAYMENT_FAILED             # Payment declined/failed
REFUND_INITIATED           # Refund requested
REFUND_COMPLETED           # Refund successfully processed
DISPUTE_OPENED             # Chargeback/dispute opened
DISPUTE_RESOLVED           # Dispute resolved
```

**E-Commerce: Cart (4 types)**
```python
CART_UPDATED               # Cart item added/removed/quantity changed
CHECKOUT_STARTED           # Checkout process initiated
CHECKOUT_COMPLETED         # Checkout successful
CHECKOUT_ABANDONED         # Cart abandoned (funnel analysis)
```

**AI Measurement (6 types)**
```python
MEASUREMENT_CREATED        # Measurement record created
MEASUREMENT_UPDATED        # Measurement updated
MEASUREMENT_DELETED        # Measurement deleted
AI_ANALYSIS_STARTED        # AI analysis job started
AI_ANALYSIS_COMPLETED      # AI analysis successful
AI_ANALYSIS_FAILED         # AI analysis failed
```

**System (4 types)**
```python
SYSTEM_ERROR               # Unexpected system error
API_CALL                   # External API called
WEBHOOK_RECEIVED           # Inbound webhook received
CELERY_TASK_FAILED         # Background job failed
```

---

## Django Admin Integration

### Read-Only Audit Dashboard

Navigate to **Django Admin → Audit Logs → Audit Event Logs**

**Features:**
- ✅ **Read-only** — no create/edit/delete via admin
- ✅ **Color-coded badges** — severity (red=critical, orange=warning) + category
- ✅ **Full-text search** — actor_email, IP, action, resource_id
- ✅ **Advanced filters** — by event_type, severity, category, is_compliance
- ✅ **Rich detail view** — organized fieldsets with collapse sections
- ✅ **50 rows per page** — optimized for large datasets
- ✅ **Date hierarchy** — quick drill-down by date
- ✅ **Superadmin-only** — `has_view_permission` returns `is_superuser`

**List Display:**
```
created_at | Severity | Category | Event Type | Actor Email | IP | Resource | Status
───────────┼──────────┼──────────┼────────────┼─────────────┼────┼──────────┼──────
2026-03-19 |   🔴 ERR |  PAYMENT | PAYMENT_FAILED | bob@sho... | 192... | Order | 402
2026-03-19 |   ⚠ WAR |   SECURITY | FAILED_LOGINS_EXCEEDED | eve@... | 10... | User | 429
2026-03-19 |   ℹ INF |  AUTH | LOGIN_SUCCESS | alice@... | 172... | User | 200
```

---

## Middleware: Auto-Context Capture

### AuditContextMiddleware

**File:** `apps/audit_logs/middleware.py`

Automatically captures HTTP request context in thread-local storage so `AuditService.log()` doesn't require passing `request=` explicitly.

**Configured in:**
```python
# backend/config/base.py
MIDDLEWARE = [
    ...
    'apps.audit_logs.middleware.AuditContextMiddleware',
    ...
]
```

**What it captures:**
- `ip_address` — Real IP via `X-Forwarded-For` chain (leftmost is real client)
- `user_agent` — Full User-Agent header
- `request_method` — GET / POST / PUT / PATCH / DELETE
- `request_path` — URL path (e.g., `/api/v1/orders/`)
- `actor` — Authenticated user (None if anonymous)
- `actor_email` — Email snapshot

**Usage without middleware:**
```python
# Without middleware, must pass request explicitly
AuditService.log(
    event_type=EventType.LOGIN_SUCCESS,
    event_category=EventCategory.AUTHENTICATION,
    action="...",
    request=request,  # ← Must provide
)
```

**Usage with middleware:**
```python
# With middleware, context auto-filled from thread-local
AuditService.log(
    event_type=EventType.LOGIN_SUCCESS,
    event_category=EventCategory.AUTHENTICATION,
    action="...",
    # ← request= not required; context auto-populated from middleware
)
```

---

## Admin Actions Audit (AuditedModelAdmin)

### Mixin for Grand Staff Accountability

**File:** `apps/audit_logs/mixins.py`

Automatically logs every admin save, delete, and bulk delete action to audit trail with before/after diffs.

### Integration

**Step 1: Import the mixin**
```python
from apps.audit_logs.mixins import AuditedModelAdmin
```

**Step 2: Add to ModelAdmin MRO** (before `admin.ModelAdmin`)
```python
@admin.register(MyModel)
class MyModelAdmin(AuditedModelAdmin, admin.ModelAdmin):
    list_display = ('name', 'created_at')
    # ... rest of admin config
```

**What it captures automatically:**
- ✅ **save_model(…, change=False)** → `ADMIN_ACTION` with new_values
- ✅ **save_model(…, change=True)** → `ADMIN_ACTION` with old_values + new_values diff
- ✅ **delete_model()** → `ADMIN_ACTION` with old_values snapshot
- ✅ **delete_queryset()** → `ADMIN_BULK_DELETE` with affected PKs in metadata
- ✅ **Sensitive field redaction** — passwords, secrets set to `***REDACTED***`
- ✅ **Before/after comparison** — only shows changed fields
- ✅ **Actor (staff user)** — auto-resolved from request
- ✅ **IP address** — captured from middleware
- ✅ **Compliance flag** — `is_compliance=True` for 7-year retention

### Example Output

```python
# Admin clicks "Save" on User form, changes email
# → Automatically logs:
AuditEventLog.objects.create(
    event_type="admin_action",
    event_category="admin",
    action="Admin updated UnifiedUser (pk=550e8400...) — fields: email, phone",
    actor=request.user,  # Staff member
    actor_email=request.user.email,
    resource_type="UnifiedUser",
    resource_id="550e8400...",
    old_values={
        "email": "alice@old.com",
        "phone": "+234901234567",
        "password": "***REDACTED***",  # Never logged in cleartext
    },
    new_values={
        "email": "alice@new.com",
        "phone": "+234901234567",
        "password": "***REDACTED***",
    },
    is_compliance=True,  # 7-year retention
    severity="info",
    ip_address="192.168.1.100",
    request_method="POST",
    request_path="/admin/authentication/unifieduser/550e8400.../change/",
    response_status=302,
)
```

---

## Step-by-Step Integration Guide for New Apps

### For `apps/orders` (E-Commerce Orders)

#### Step 1: Import AuditService in your view/service

**File:** `apps/orders/services/order_service.py`

```python
from apps.audit_logs.services.audit import AuditService
from apps.audit_logs.models import EventType, EventCategory
```

#### Step 2: Log order creation

**In your OrderService.create() method:**

```python
class OrderService:
    @staticmethod
    def create_order(user, cart_items, shipping_address, request):
        """Create an order from cart."""

        # ... validate / process cart items ...

        order = Order.objects.create(
            user=user,
            total_amount=total,
            status="pending",
        )

        # ✅ LOG EVENT: Order created
        AuditService.log(
            event_type=EventType.ORDER_CREATED,
            event_category=EventCategory.ORDER,
            action=f"Order {order.id} created with {len(cart_items)} items",
            request=request,
            resource_type="Order",
            resource_id=str(order.pk),
            metadata={
                "item_count": len(cart_items),
                "total_amount_kobo": str(int(total * 100)),
                "currency": "NGN",
                "shipping_to": shipping_address.country,
            },
            is_compliance=True,  # Orders are business-critical
        )

        return order
```

#### Step 3: Log order status changes

**In your OrderService.update_status() method:**

```python
def update_status(order, new_status, request):
    """Update order status (pending → processing → shipped → delivered)."""

    old_status = order.status
    order.status = new_status
    order.save()

    # ✅ LOG EVENT: Order status changed
    AuditService.log(
        event_type=EventType.ORDER_UPDATED,
        event_category=EventCategory.ORDER,
        action=f"Order {order.id} status changed: {old_status} → {new_status}",
        request=request,
        resource_type="Order",
        resource_id=str(order.pk),
        old_values={"status": old_status},
        new_values={"status": new_status},
        metadata={
            "transition": f"{old_status}→{new_status}",
            "timestamp_utc": str(datetime.utcnow()),
        },
        is_compliance=True,
    )
```

#### Step 4: Log order cancellation/fulfillment

```python
def cancel_order(order, reason, request):
    """Cancel an order."""

    order.status = "cancelled"
    order.cancelled_at = datetime.now()
    order.cancellation_reason = reason
    order.save()

    # ✅ LOG EVENT: Order cancelled
    AuditService.log(
        event_type=EventType.ORDER_CANCELLED,
        event_category=EventCategory.ORDER,
        action=f"Order {order.id} cancelled: {reason}",
        severity="warning",  # Order cancellation is notable
        request=request,
        resource_type="Order",
        resource_id=str(order.pk),
        old_values={"status": "pending", "cancelled_at": None},
        new_values={
            "status": "cancelled",
            "cancelled_at": str(order.cancelled_at),
            "cancellation_reason": reason,
        },
        is_compliance=True,
    )
```

#### Step 5: Enable admin audit (optional but recommended)

**File:** `apps/orders/admin.py`

```python
from apps.audit_logs.mixins import AuditedModelAdmin

@admin.register(Order)
class OrderAdmin(AuditedModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'user', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'user__email')
    readonly_fields = ('id', 'created_at', 'updated_at')
    # ← AuditedModelAdmin automatically logs all admin actions
```

### For `apps/payments` (Payment Processing)

#### Step 1: Log payment initiation

**File:** `apps/payments/services/payment_service.py`

```python
from apps.audit_logs.services.audit import AuditService
from apps.audit_logs.models import EventType, EventCategory, SeverityLevel

class PaymentService:
    @staticmethod
    def initiate_payment(order, customer_email, amount, gateway, request):
        """Initiate payment transaction."""

        # ✅ LOG EVENT: Payment initiated
        AuditService.log(
            event_type=EventType.PAYMENT_INITIATED,
            event_category=EventCategory.PAYMENT,
            action=f"Payment ₦{amount:,.2f} initiated for Order {order.id} via {gateway}",
            severity="info",
            request=request,
            resource_type="Order",
            resource_id=str(order.pk),
            metadata={
                "amount_kobo": str(int(amount * 100)),
                "currency": "NGN",
                "gateway": gateway,
                "customer_email": customer_email,
            },
            is_compliance=True,  # Financial transaction
        )
```

#### Step 2: Log successful payment

**Called from Paystack webhook handler:**

```python
def handle_paystack_webhook(payload, request=None):
    """Handle Paystack payment webhook."""

    reference = payload.get('reference')
    amount_kobo = payload.get('amount')
    status = payload.get('status')
    customer_email = payload.get('customer', {}).get('email')

    if status == 'success':
        order = Order.objects.get(external_reference=reference)
        order.status = 'paid'
        order.save()

        # ✅ LOG EVENT: Payment successful (critical for PCI-DSS)
        AuditService.log(
            event_type=EventType.PAYMENT_SUCCESS,
            event_category=EventCategory.PAYMENT,
            action=f"Payment ₦{amount_kobo/100:,.2f} successful for Order {order.id}",
            severity="info",
            resource_type="Order",
            resource_id=str(order.pk),
            metadata={
                "payment_ref": reference,
                "amount_kobo": str(amount_kobo),
                "gateway": "paystack",
                "status_code": status,
                "customer_email": customer_email,
                "receipt_url": payload.get('authorization', {}).get('receipt_number'),
            },
            is_compliance=True,  # PCI-DSS Level 1 compliance
        )
```

#### Step 3: Log payment failures

```python
def handle_payment_failure(order, error_reason, error_code, request=None):
    """Log payment failure."""

    # ✅ LOG EVENT: Payment failed
    AuditService.log(
        event_type=EventType.PAYMENT_FAILED,
        event_category=EventCategory.PAYMENT,
        action=f"Payment failed for Order {order.id}: {error_reason}",
        severity="warning",  # Failed payment is notable
        resource_type="Order",
        resource_id=str(order.pk),
        error_message=f"{error_code}: {error_reason}",
        metadata={
            "error_code": error_code,
            "error_reason": error_reason,
            "attempted_amount_kobo": str(int(order.total * 100)),
        },
        is_compliance=True,  # Financial audit trail
    )
```

#### Step 4: Log refunds

```python
def initiate_refund(order, refund_reason, refund_amount, request):
    """Initiate refund for an order."""

    # ✅ LOG EVENT: Refund initiated
    AuditService.log(
        event_type=EventType.REFUND_INITIATED,
        event_category=EventCategory.PAYMENT,
        action=f"Refund ₦{refund_amount:,.2f} initiated for order {order.id}",
        severity="warning",  # Refund is notable
        request=request,
        resource_type="Order",
        resource_id=str(order.pk),
        metadata={
            "refund_amount_kobo": str(int(refund_amount * 100)),
            "refund_reason": refund_reason,
            "original_transaction": str(order.payment_ref),
        },
        is_compliance=True,  # Financial compliance
    )
```

### For `apps/products` (Inventory Management)

#### Step 1: Log product creation/updates

**File:** `apps/products/services/product_service.py`

```python
from apps.audit_logs.services.audit import AuditService
from apps.audit_logs.models import EventType, EventCategory

class ProductService:
    @staticmethod
    def create_product(vendor, name, price, description, request):
        """Create a new product listing."""

        product = Product.objects.create(
            vendor=vendor,
            name=name,
            price=price,
            description=description,
        )

        # ✅ LOG EVENT: Product created
        AuditService.log(
            event_type=EventType.ADMIN_ACTION,  # Or custom event type
            event_category=EventCategory.DATA_MODIFICATION,
            action=f"Product '{name}' created by vendor {vendor.email}",
            request=request,
            resource_type="Product",
            resource_id=str(product.pk),
            new_values={
                "name": name,
                "price": str(price),
                "vendor_id": str(vendor.pk),
            },
            is_compliance=False,  # Not financial
        )

        return product
```

#### Step 2: Log price/inventory changes

```python
def update_product(product, updates, request):
    """Update product fields (e.g., price, stock)."""

    old_values = {
        "price": str(product.price),
        "stock_quantity": product.stock_quantity,
    }

    for key, value in updates.items():
        setattr(product, key, value)
    product.save()

    new_values = {
        "price": str(product.price),
        "stock_quantity": product.stock_quantity,
    }

    # ✅ LOG EVENT: Product updated
    AuditService.log(
        event_type=EventType.ADMIN_ACTION,
        event_category=EventCategory.DATA_MODIFICATION,
        action=f"Product '{product.name}' updated: {list(updates.keys())}",
        request=request,
        resource_type="Product",
        resource_id=str(product.pk),
        old_values=old_values,
        new_values=new_values,
        metadata={"updated_fields": list(updates.keys())},
        is_compliance=False,
    )
```

---

## Advanced Usage & Querying

### Query Recent Login Attempts (Security)

```python
from apps.audit_logs.models import AuditEventLog, EventType
from django.utils import timezone
from datetime import timedelta

# Get failed logins in last 24 hours
recent_failures = AuditEventLog.objects.filter(
    event_type=EventType.LOGIN_FAILED,
    created_at__gte=timezone.now() - timedelta(hours=24),
).order_by('-created_at')

for event in recent_failures:
    print(f"{event.actor_email} failed login @ {event.ip_address}")
```

### Query Compliance Events

```python
# Get all compliance-flagged events for audit review
compliance_events = AuditEventLog.objects.filter(
    is_compliance=True,
    event_category__in=['payment', 'admin', 'security'],
    created_at__gte='2026-01-01',
).order_by('-created_at')

for event in compliance_events:
    print(f"[{event.severity}] {event.action} @ {event.created_at}")
```

### Query Resource Audit Trail

```python
# Get full audit trail for a specific Order
order_id = "order_abc123"
order_timeline = AuditEventLog.objects.filter(
    resource_type="Order",
    resource_id=order_id,
).order_by('created_at')

for event in order_timeline:
    print(f"{event.created_at}: {event.event_type} by {event.actor_email}")
    if event.old_values and event.new_values:
        print(f"  Changes: {event.old_values} → {event.new_values}")
```

### Query User Action History

```python
# Get all actions by a specific user (actor)
user_actions = AuditEventLog.objects.filter(
    actor_email="alice@example.com",
    created_at__gte='2026-03-01',
).select_related('actor').order_by('-created_at')

for event in user_actions:
    print(f"{event.event_type}: {event.action}")
```

### Export Compliance Report

```python
# Get compliance events for a date range (e.g., monthly audits)
import csv
from django.utils import timezone
from datetime import timedelta

start_date = timezone.now() - timedelta(days=30)
compliance_report = AuditEventLog.objects.filter(
    is_compliance=True,
    created_at__gte=start_date,
).values(
    'created_at', 'actor_email', 'event_type', 'action',
    'resource_type', 'resource_id', 'severity'
).order_by('created_at')

with open('compliance_audit_2026_03.csv', 'w') as f:
    writer = csv.DictWriter(f, fieldnames=[...])
    writer.writeheader()
    writer.writerows(compliance_report)
```

---

## Security & Compliance

### Design Principles

| Principle | Implementation |
|---|---|
| **Immutable** | No UPDATE / DELETE after creation; admin read-only |
| **Non-Blocking** | Async Celery dispatch; never slows HTTP request |
| **Fault-Tolerant** | Sync fallback if broker down; events never dropped |
| **Sensitive Data Redacted** | Passwords, secrets replaced with `***REDACTED***` |
| **Actor Snapshot** | `actor_email` preserved even if user hard-deleted |
| **Context Rich** | IP, device, browser, OS captured for fraud detection |
| **Compliance Ready** | 7-year retention for financial/regulatory requirements |

### Data Redaction

**Automatically redacted fields** in `AuditedModelAdmin` and diffs:
```python
_REDACTED_FIELDS = frozenset({
    "password", "api_secret", "secret_key", "token",
    "otp_secret", "otp_base32",
})

# Also redacts fields matching:
if "password" in key.lower() or "secret" in key.lower():
    data[k] = "***REDACTED***"
```

### Compliance Retention

```python
# Financial compliance (7 years)
AuditService.log(
    ...,
    event_type=EventType.PAYMENT_SUCCESS,
    is_compliance=True,  # ← 2555 days (7 years) retention by default
)

# Non-compliance (shorter retention possible)
AuditService.log(
    ...,
    event_type=EventType.LOGIN_SUCCESS,
    is_compliance=False,  # ← Default 90-day logger rotation
)
```

### GDPR Data Subject Access Request (DSAR)

```python
# Get all audit events for a user (GDPR Article 15)
user_email = "alice@example.com"
user_events = AuditEventLog.objects.filter(
    actor_email=user_email,
).order_by('created_at')

# Export as JSON for user
import json
events_json = [
    {
        'created_at': str(e.created_at),
        'event_type': e.event_type,
        'action': e.action,
        'ip_address': e.ip_address,
        'device_type': e.device_type,
        'country': e.country,
    }
    for e in user_events
]

with open(f'dsar_{user_email}.json', 'w') as f:
    json.dump(events_json, f, indent=2)
```

---

## File Structure

```
apps/audit_logs/
├── __init__.py
├── admin.py                    # AuditEventLogAdmin — read-only superadmin interface
├── apps.py                     # AppConfig
├── middleware.py               # AuditContextMiddleware — thread-local context capture
├── mixins.py                   # AuditedModelAdmin — auto-log admin actions
├── models.py                   # AuditEventLog model with 51 event types, 15 categories
├── services/
│   ├── __init__.py
│   └── audit.py               # AuditService.log() — high-level API
├── tasks.py                    # write_audit_event — Celery task with retry/fallback
├── migrations/
│   ├── 0001_initial_audit_event_log.py
│   └── 0002_auditeventlog_correlation_id_...py
├── README.md                   # This file
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_services.py
    ├── test_admin.py
    └── test_middleware.py
```

---

## Database Schema & Indexes

### Main Model: AuditEventLog

```sql
CREATE TABLE audit_logs_auditeventlog (
    id UUID PRIMARY KEY,
    event_type VARCHAR(60) NOT NULL,
    event_category VARCHAR(60) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    action TEXT NOT NULL,
    actor_id UUID REFERENCES authentication_unifieduser(id) ON DELETE SET NULL,
    actor_email VARCHAR(254),
    ip_address INET,
    user_agent TEXT,
    device_type VARCHAR(30),
    browser_family VARCHAR(80),
    os_family VARCHAR(80),
    country VARCHAR(100),
    correlation_id VARCHAR(64),
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    request_method VARCHAR(10),
    request_path VARCHAR(500),
    response_status SMALLINT,
    duration_ms FLOAT,
    old_values JSONB,
    new_values JSONB,
    metadata JSONB,
    error_message TEXT,
    is_compliance BOOLEAN NOT NULL DEFAULT FALSE,
    retention_days INTEGER NOT NULL DEFAULT 2555,
    created_at TIMESTAMP NOT NULL
);
```

### Optimized Indexes (11 Composite)

```sql
-- Time-range queries
CREATE INDEX idx_ael_created ON audit_logs_auditeventlog(created_at DESC);

-- Actor lookup
CREATE INDEX idx_ael_actor ON audit_logs_auditeventlog(actor_id, created_at DESC);
CREATE INDEX idx_ael_email ON audit_logs_auditeventlog(actor_email, created_at DESC);

-- Event filtering
CREATE INDEX idx_ael_etype ON audit_logs_auditeventlog(event_type, created_at DESC);
CREATE INDEX idx_ael_ecat ON audit_logs_auditeventlog(event_category, created_at DESC);

-- Security dashboard
CREATE INDEX idx_ael_sev ON audit_logs_auditeventlog(severity, created_at DESC);
CREATE INDEX idx_ael_ip ON audit_logs_auditeventlog(ip_address, created_at DESC);

-- Resource lookup
CREATE INDEX idx_ael_resource ON audit_logs_auditeventlog(resource_type, resource_id);

-- Compliance reports
CREATE INDEX idx_ael_compliance ON audit_logs_auditeventlog(is_compliance, created_at DESC);

-- Tracing
CREATE INDEX idx_ael_corr ON audit_logs_auditeventlog(correlation_id);
CREATE INDEX idx_ael_country ON audit_logs_auditeventlog(country, created_at DESC);
```

---

## Troubleshooting

### Q: Events not being logged?

**Check:**
1. Middleware registered in `INSTALLED_APPS` and `MIDDLEWARE`
```python
INSTALLED_APPS = [..., 'apps.audit_logs', ...]
MIDDLEWARE = [..., 'apps.audit_logs.middleware.AuditContextMiddleware', ...]
```

2. Celery broker running:
```bash
# If using Redis
redis-cli PING  # Should return PONG
# If using RabbitMQ
rabbitmqctl status
```

3. Celery worker running:
```bash
celery -A backend worker -l info
```

4. Check logs:
```bash
tail -f logs/audit.log
# Or check Django logs
python manage.py runserver --verbosity 3 2>&1 | grep -i audit
```

### Q: Celery broker is down — will events be lost?

**No.** AuditService implements automatic fallback:
```
Try Celery task → Broker down? → Write synchronously to DB
               │
               ├─ Success: async write
               └─ Failure: sync write (events NEVER lost)
```

### Q: How do I query for fraud suspicious activity?

```python
from apps.audit_logs.models import AuditEventLog, EventType
from django.utils import timezone
from datetime import timedelta

# Get failed logins from single IP in last hour
suspicious_ips = AuditEventLog.objects.filter(
    event_type__in=[
        EventType.LOGIN_FAILED,
        EventType.FAILED_LOGINS_EXCEEDED,
    ],
    created_at__gte=timezone.now() - timedelta(hours=1),
).values('ip_address').annotate(Count('id')).filter(id__count__gte=5)

for entry in suspicious_ips:
    print(f"🚨 Suspicious IP: {entry['ip_address']} ({entry['id__count']} attempts)")
```

### Q: Can I delete audit logs?

**No, by design:**
- Application code: no `delete()` method exposed
- Django admin: no delete permission (even for superuser)
- Reason: audit trail must be tamper-proof for compliance

### Q: What's the retention policy?

```python
# Default for compliance = 7 years
retention_days = 2555  # 365.25 * 7

# Can be customized per-event
AuditService.log(
    ...,
    is_compliance=True,
    retention_days=365,  # Override to 1 year
)

# Retention enforcement (e.g., Celery periodic task)
from apps.audit_logs.models import AuditEventLog
from django.utils import timezone
from datetime import timedelta

expired = AuditEventLog.objects.filter(
    is_compliance=False,
    created_at__lt=timezone.now() - timedelta(days=90),
)
expired_count = expired.count()
# Manual delete or archive to cold storage
```

---

## Event Limits & Rate Limiting

```python
# AuditService logs a max of 1 event per millisecond per process
# High-volume logging (e.g., per-request analytics) should use separate table

# ❌ Anti-pattern: audit every API read
for product in Product.objects.all():
    AuditService.log(...)  # DON'T — creates million rows

# ✅ Pattern: audit business-critical events only
AuditService.log(event_type=EventType.PAYMENT_SUCCESS, ...)  # DO
```

---

**Last updated:** 2026-03-19 · **Maintainer:** Fashionistar Engineering
