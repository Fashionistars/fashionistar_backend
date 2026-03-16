# apps/common — Developer Reference

> **Version** 2026-03-16 · **Django** 6.0.2 · **Maintainer** Fashionistar Engineering

This document is the canonical reference for every class, model, mixin, middleware, permission, utility, task, signal, event handler, and admin component in `fashionistar_backend/apps/common`. **Read it fully before adding or modifying anything in this app.** Both human developers and AI agents must read this line-by-line before making changes.

---

## Table of Contents

1. [Overview & Role System](#overview--role-system)
2. [Architecture Diagram](#architecture-diagram)
3. [Security & Audit Logging](#security--audit-logging)
4. [Event Message Bus (`events.py`)](#event-message-bus-eventspy)
5. [Event Handlers (`event_handlers.py`)](#event-handlers-event_handlerspy)
6. [Middleware](#middleware)
7. [Models](#models)
   - [SoftDeleteModel](#softdeletemodel)
   - [DeletedRecords](#deletedrecords)
   - [DeletionAuditCounter](#deletionauditcounter)
   - [ModelAnalytics](#modelanalytics)
   - [TimeStampModel](#timestampmodel)
   - [HardDeleteMixin](#harddeletemixin)
8. [Managers](#managers)
9. [Permissions](#permissions)
10. [Admin Mixins](#admin-mixins)
11. [Tasks (Celery)](#tasks-celery)
12. [Signals (Analytics Only)](#signals-analytics-only)
13. [Cloudinary Upload Utilities](#cloudinary-upload-utilities)
14. [Redis Utilities](#redis-utilities)
15. [Exceptions](#exceptions)
16. [Renderers](#renderers)
17. [Admin Registrations](#admin-registrations)
18. [How to Add a New Model](#how-to-add-a-new-model)
19. [How to Add a New Business Event](#how-to-add-a-new-business-event)
20. [Future App Integration Guide](#future-app-integration-guide)
21. [Stress Test Results](#stress-test-results)

---

## Overview & Role System

`apps.common` is the platform-wide shared infrastructure layer. It underpins security, database integrity, analytics, error handling, media uploads, and cross-cutting concerns for the modular monolith architecture.

It provides:

| Concern | Solution |
|---|---|
| Soft-delete for any model | `SoftDeleteModel` abstract base |
| Forensic archive of deletes | `DeletedRecords` model |
| Per-action deletion counters | `DeletionAuditCounter` |
| Full lifecycle analytics | `ModelAnalytics` (auto-tracked via signals) |
| Business lifecycle events | `EventBus` + `event_handlers.py` (no Django signals) |
| Background notifications | Celery tasks via `_fire_and_forget_notification` |
| Race-safe counter writes | F()-first-UPDATE + IntegrityError retry in `_adjust()` |
| Global change auditing | `django-auditlog` (field-level diffs for every model) |
| Security Request Trace | `SecurityAuditMiddleware` logs IP/Role/Method for SIEM |
| Async media uploads | Two-phase Cloudinary direct-upload + webhook |
| Redis caching | Presign params cache, API response caching |

The platform recognizes 7 primary user roles (checked via `getattr(user, 'role', None)` and mapped in `permissions.py`):

1. **Client**: Shoppers and consumers.
2. **Vendor**: Sellers who own stores and list products.
3. **Support**: Customer service representatives.
4. **Reviewer / Editor**: Content moderation and review.
5. **Assistant / Sales**: Sales analytics and marketing.
6. **Admin**: Staff with elevated management rights.
7. **Superadmin**: Full platform access (`is_superuser=True`).

**Golden rule for developers**: Every feature in this app is designed for **high concurrency** and **fire-and-forget** patterns. Do not write synchronous blocking operations here. Use Celery (`transaction.on_commit`) and the `EventBus` for cross-app boundaries. No operation here must ever slow down an HTTP response or admin action.

---

## Architecture Diagram

```
HTTP Request / Admin Action
        │
        ▼
  Model .save() / .delete()
        │
        ├─► post_save(created=True)  ──► ModelAnalytics.record_created()   [signals.py]
        ├─► post_save(created=False) ──► ModelAnalytics.record_updated()   [signals.py]
        ├─► post_delete              ──► ModelAnalytics.record_hard_deleted() [signals.py]
        │
        ├─► SoftDeleteModel.soft_delete() ──► record_soft_deleted() + notify
        ├─► SoftDeleteModel.restore()     ──► record_restored() + notify
        │
        ├─► EventBus.emit_on_commit('user.registered', ...)
        │       │           [event_handlers.py → Celery task]
        │
        └─► transaction.on_commit
                │
                ▼
         Celery Task (background)
                │
                ▼
         ModelAnalytics._adjust()
         [F()-UPDATE → IntegrityError-safe INSERT]
         Race-condition proof at 100K req/s
```

---

## Security & Audit Logging

To comply with enterprise standards (Amazon, Etsy scale), every HTTP interaction with the backend is captured in a comprehensive Security Audit Trail using the `security` logger.

### SecurityAuditMiddleware

**File:** `apps/common/middleware.py`

- **Client IP**: Extracted securely via `X-Forwarded-For` chain (leftmost real IP).
- **HTTP Context**: Method GET/POST/PUT, requested URL path, and query string.
- **Trace ID**: `X-Request-ID` attached to all logs for distributed tracing.
- **User Context**: Extracts `user_id` and the explicit user `role` from the request.
- **Status Classification**: `INFO` (2xx), `WARNING` (401/403), `ERROR` (5xx).

---

## Event Message Bus (`events.py`)

**File:** `apps/common/events.py`
**Singleton:** `from apps.common.events import event_bus`

Replaces ALL Django signals for **business logic**. Analytics signals (`signals.py`) are the only remaining use of Django signals — they only update counters.

### Key Methods

| Method | Description |
|---|---|
| `event_bus.subscribe(event, handler)` | Register a handler for a named event |
| `event_bus.emit(event, **payload)` | Fire immediately (background thread) |
| `event_bus.emit_on_commit(event, **payload)` | Fire AFTER current DB transaction commits |
| `event_bus.emit_async(event, **payload)` | Async-native emit for ASGI views |

### Usage

```python
from apps.common.events import event_bus

# Publisher (in a service)
with transaction.atomic():
    user = UnifiedUser.objects.create_user(...)
    event_bus.emit_on_commit(
        'user.registered',
        user_uuid=str(user.pk),
        email=user.email,
        role=user.role,
    )

# Subscriber (in event_handlers.py, wired in apps.py ready())
def on_user_registered(user_uuid, email, role, **kwargs):
    send_welcome_email_task.apply_async(kwargs=dict(user_uuid=user_uuid))
```

### Registered Events (2026-03-16)

| Event | Publisher | Handler |
|---|---|---|
| `user.registered` | `authentication/services/registration/sync_service.py` | `event_handlers.on_user_registered` |

### Integration for Future Apps

```python
# apps/orders/services/order_service.py
from apps.common.events import event_bus
event_bus.emit_on_commit('order.placed', order_id=str(order.pk), user_id=str(user.pk))

# apps/common/event_handlers.py — add handler here
def on_order_placed(order_id, **kwargs):
    send_order_confirmation_task.apply_async(...)

# apps/common/apps.py — subscribe in CommonConfig.ready()
event_bus.subscribe('order.placed', on_order_placed)
```

---

## Event Handlers (`event_handlers.py`)

**File:** `apps/common/event_handlers.py`
**Connected in:** `apps/common/apps.py:CommonConfig.ready()`

This is the ONLY place in `apps.common` that handles business lifecycle events. All handlers:

1. Dispatch a Celery task (non-blocking) — **primary path**
2. Fall back to sync `get_or_create()` if Celery/Redis is unavailable — **fallback**
3. Are **idempotent** — called twice with the same payload produces no duplicates
4. Accept `**kwargs` to stay forward-compatible with future payload additions

### Current Handlers

| Handler | Event | Celery Task |
|---|---|---|
| `on_user_registered` | `user.registered` | `upsert_user_lifecycle_registry` |

---

## Middleware

**File:** `apps/common/middleware.py`

1. **`RequestIDMiddleware`**: Injects `UUID4` onto `request.request_id` + `X-Request-ID` response header.
2. **`RequestTimingMiddleware`**: Logs execution times.
3. **`SecurityAuditMiddleware`**: Captures global 7-role requests with X-Forwarded-For IP resolution.

---

## Models

### SoftDeleteModel
**File:** `apps/common/models.py`

Abstract base class. Inherit instead of `models.Model` for any model that needs soft-delete.

#### Fields

| Field | Type | Description |
|---|---|---|
| `is_deleted` | `BooleanField` | `True` = soft-deleted, hidden from default queries |
| `deleted_at` | `DateTimeField` | Timestamp of last soft-delete (null when active) |

#### Methods

| Method | Description |
|---|---|
| `soft_delete()` | Archives to `DeletedRecords`, sets `is_deleted=True` via `QuerySet.update()` |
| `restore()` | Clears `is_deleted=False`, purges `DeletedRecords` entry |
| `_fire_and_forget_notification(action)` | Dispatches email/SMS Celery tasks |

#### Default Manager Behaviour

| Manager | Queryset |
|---|---|
| `Model.objects` (default) | **Alive only** (`is_deleted=False`) |
| `Model.objects.all_with_deleted()` | All records including soft-deleted |
| `Model.objects.deleted_only()` | Only soft-deleted |

> [!IMPORTANT]
> Always call `all_with_deleted()` when querying records that may be soft-deleted.

#### How to inherit

```python
from apps.common.models import SoftDeleteModel

class Product(SoftDeleteModel):
    name = models.CharField(max_length=200)
```

---

### DeletedRecords

Forensic archive. One row per soft-deleted record. Created by `soft_delete()`, removed by `restore()`.

| Field | Description |
|---|---|
| `model_name` | Django model class name |
| `record_id` | PK of the deleted record (string) |
| `deleted_at` | Timestamp of deletion |
| `data` | JSON snapshot at deletion time |

---

### DeletionAuditCounter

One row per `(model_name, action)` pair. Tracks cumulative totals of `soft_delete`, `hard_delete`, `restore`.

```python
DeletionAuditCounter.increment(model_name='Product', action='soft_delete', count=5)
```

---

### ModelAnalytics

The heart of the analytics system. **One row per Django model**.

| Field | Meaning |
|---|---|
| `total_created` | Cumulative creates. **Never decrements.** |
| `total_active` | Currently alive |
| `total_updated` | Cumulative saves on existing records |
| `total_soft_deleted` | Currently soft-deleted (recoverable) |
| `total_hard_deleted` | Cumulative permanent purges. **Never decrements.** |

**Identity equation**: `total_created = total_active + total_soft_deleted + total_hard_deleted`

**High-level API**:
```python
ModelAnalytics.record_created(model_name, app_label)
ModelAnalytics.record_updated(model_name, app_label)
ModelAnalytics.record_soft_deleted(model_name, app_label)
ModelAnalytics.record_restored(model_name, app_label)
ModelAnalytics.record_hard_deleted(model_name, app_label, was_soft_deleted=False)
```

`_adjust()` uses F()-expressions as a race-safe counter pattern (no `select_for_update()` deadlocks, safe at 100K+ concurrent requests).

> [!WARNING]
> Never call `_adjust()` or `_dispatch()` directly. Always use the `record_*` class methods.

---

## Managers

| Manager | Usage |
|---|---|
| `SoftDeleteManager` (default) | Filters `is_deleted=False`. Used by `Model.objects`. |
| `AllObjectsManager` | Exposes `.all_with_deleted()` and `.deleted_only()`. |

---

## Permissions

**File:** `apps/common/permissions.py`

| Permission | Role required |
|---|---|
| `IsVendor` | `vendor` |
| `IsClient` | `client` |
| `IsStaff` | `staff`, `admin`, `editor`, `assistant` |
| `IsSupport` | `support` |
| `IsEditor` | `editor` |
| `IsSales` | `assistant` |
| `IsOwner` | Resource-level: `obj.user == request.user` |

Both synchronous `has_permission` and async `has_permission_async` provided.

---

## Admin Mixins

### `SoftDeleteAdminMixin`

```python
from apps.common.admin_mixins import SoftDeleteAdminMixin

@admin.register(Product)
class ProductAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('name', '_is_deleted_badge')
    actions = ['soft_delete_selected', 'restore_selected', 'hard_delete_selected']
```

### `EnterpriseImportExportMixin`

Provides streaming CSV export (100K+ rows, no OOM), atomic chunked import with dry-run + rollback.

```python
from apps.common.admin_import_export import EnterpriseImportExportMixin, EnterpriseModelResource

class ProductResource(EnterpriseModelResource):
    class Meta:
        model = Product
        fields = ('id', 'name', 'price', 'is_deleted')
        import_id_fields = ['id']

@admin.register(Product)
class ProductAdmin(EnterpriseImportExportMixin, admin.ModelAdmin):
    resource_classes = [ProductResource]
```

> [!NOTE]
> Uses `get_export_resource_classes()` (django-import-export ≥4.0, plural list form).

---

## Tasks (Celery)

**Files:** `apps/common/tasks/`

| Task | Description |
|---|---|
| `keep_service_awake` | Periodic ping to prevent Render spin-down |
| `send_account_status_email` | Email on soft-delete/restore/hard-delete |
| `send_account_status_sms` | SMS on same events |
| `update_model_analytics_counter` | Background `ModelAnalytics._adjust()` |
| `upsert_user_lifecycle_registry` | Create/update permanent user lifecycle record |
| `process_cloudinary_upload_webhook` | Route Cloudinary webhook payload to model field |
| `generate_eager_transformations` | Trigger server-side Cloudinary transforms |
| `purge_cloudinary_cache` | Invalidate Cloudinary CDN cache |

All tasks use `apply_async(retry=False, ignore_result=True)` — true fire-and-forget.

---

## Signals (Analytics Only)

**File:** `apps/common/signals.py` · **Registered in:** `apps/common/apps.py:CommonConfig.ready()`

> [!IMPORTANT]
> Signals in this project are **analytics-only**. All business logic uses the `EventBus` instead. NEVER add cross-app business logic to signal handlers.

| Signal | Handler | Counter updated |
|---|---|---|
| `post_save(created=True)` | `on_model_created` | `total_created`, `total_active` |
| `post_save(created=False)` | `on_model_updated` | `total_updated` |
| `post_delete` | `on_model_hard_deleted` | `total_hard_deleted` |

**Excluded models** (never tracked — prevents feedback loops):
```python
_EXCLUDED_MODEL_NAMES = frozenset({
    'Session', 'ContentType', 'Permission', 'LogEntry',
    'BlacklistedToken', 'OutstandingToken',
    'ModelAnalytics', 'DeletionAuditCounter', 'DeletedRecords',
    'CrontabSchedule', 'IntervalSchedule', 'PeriodicTask', 'SolarSchedule', 'ClockedSchedule',
    'MemberIDCounter',   # ← write-once atomic counter; tracking saves creates infinite loop
})
```

**Smart update filter**: Skips saves where `update_fields` contains only `{is_deleted, deleted_at}`.

---

## Cloudinary Upload Utilities

**File:** `apps/common/utils/cloudinary.py`
**API:** `POST /api/v1/upload/presign/` → direct upload → `POST /api/v1/upload/webhook/cloudinary/`

### Two-Phase Direct Upload Architecture

```
1. Frontend → POST /api/v1/upload/presign/ (JWT required)
   ← returns: public_id, timestamp, signature, api_key, folder
2. Frontend → POST https://api.cloudinary.com  (direct, NO Django server)
3. Cloudinary → POST /api/v1/upload/webhook/cloudinary/ (HMAC-SHA256 validated)
4. Django → Celery task: process_cloudinary_upload_webhook
5. Model field updated: e.g. UnifiedUser.avatar = secure_url
```

### Key Functions

```python
from apps.common.utils.cloudinary import generate_upload_signature, validate_cloudinary_signature

# Generate signed upload token
sig, timestamp = generate_upload_signature(folder='fashionistar/products', asset_type='product_image')

# Validate incoming Cloudinary webhook
is_valid = validate_cloudinary_signature(body_bytes, timestamp_header, signature_header)
```

### Asset Config Map (`_ASSET_CONFIGS`)

Covers: `avatar`, `category_image`, `brand_logo`, `product_image`, `gallery_image`,
`color_swatch`, `vendor_logo`, `blog_cover`, `collection_cover`, `profile_image`,
`measurement_photo`, `message_attachment`, and generic fallbacks.

### Integration for New Apps

When adding a new image field (e.g., `apps.vendors.Vendor.logo`):

1. Add the asset type to `_ASSET_CONFIGS` in `utils/cloudinary.py`
2. Add routing in `tasks/cloudinary.py:process_cloudinary_upload_webhook`
3. Use `models.URLField(max_length=500, blank=True, null=True)` — not `ImageField`

---

## Redis Utilities

**File:** `apps/common/utils/redis.py`

| Function | Purpose |
|---|---|
| `presign_cache_get(user_id, asset_type)` | Retrieve cached presign params |
| `presign_cache_set(user_id, asset_type, data, ttl)` | Cache presign params (default 55s) |
| `api_cache_get(key)` | API response cache read |
| `api_cache_set(key, value, ttl)` | API response cache write |
| `api_cache_delete(key)` | Cache invalidation |
| `api_cache_delete_pattern(prefix)` | Wildcard cache invalidation |

All functions degrade gracefully — if Redis is unavailable they return `None` and log a warning.

---

## Exceptions

**File:** `apps/common/exceptions.py`

Standardizes ALL error responses into a uniform JSON envelope:

```json
{
    "success": false,
    "message": "Permission denied",
    "code": "permission_denied",
    "errors": {...}
}
```

---

## Renderers

**File:** `apps/common/renderers.py`

Standard JSON payload envelopes on all successful `APIView` responses.

---

## Admin Registrations

| Admin class | Model | Access |
|---|---|---|
| `DeletedRecordsAdmin` | `DeletedRecords` | Superusers; delete cascades to source record |
| `DeletionAuditCounterAdmin` | `DeletionAuditCounter` | Superadmins only (read-only) |
| `ModelAnalyticsAdmin` | `ModelAnalytics` | Superadmins only (read-only) |

---

## How to Add a New Model

### Step 1 — Inherit `SoftDeleteModel`

```python
from apps.common.models import SoftDeleteModel

class Product(SoftDeleteModel):
    name = models.CharField(max_length=200)
```

### Step 2 — Register the ModelAdmin

```python
from apps.common.admin_mixins import SoftDeleteAdminMixin

@admin.register(Product)
class ProductAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('name', '_is_deleted_badge')
    actions = ['soft_delete_selected', 'restore_selected', 'hard_delete_selected']
```

### Step 3 — Run migrations

```bash
uv run manage.py makemigrations yourapp && uv run manage.py migrate
```

### Step 4 — Verify in admin

- **Common → Model Analytics** — a row for `YourModel` appears after the first save.
- **Common → Deletion Audit Counters** — rows appear after first soft/hard delete.

### Rules to follow

| ✅ DO | ❌ DON'T |
|---|---|
| Use `Model.objects.all_with_deleted()` for deleted records | Use `Model.objects.filter(is_deleted=True)` |
| Wrap `DeletionAuditCounter.increment()` in `try/except` | Let analytics exceptions crash user-facing code |
| Dispatch notifications via `_fire_and_forget_notification()` | Call email/SMS directly from views or signals |
| Use `record_*()` class methods for ModelAnalytics | Call `_adjust()` directly from signal handlers |
| Use `QuerySet.update()` in bulk admin actions | Loop `.save()` per record (N+1) |

---

## How to Add a New Business Event

### Step 1 — Emit (in your service)

```python
from apps.common.events import event_bus

with transaction.atomic():
    order = Order.objects.create(...)
    event_bus.emit_on_commit('order.placed', order_id=str(order.pk), user_id=str(user.pk))
```

### Step 2 — Create handler (in event_handlers.py)

```python
def on_order_placed(order_id: str, user_id: str, **kwargs) -> None:
    try:
        send_order_confirmation_task.apply_async(kwargs=dict(order_id=order_id))
    except Exception:
        # sync fallback: YourModel.objects.get_or_create(...)
        pass
```

### Step 3 — Subscribe (in apps.py CommonConfig.ready())

```python
from apps.common.event_handlers import on_order_placed
event_bus.subscribe('order.placed', on_order_placed)
```

---

## Future App Integration Guide

### apps/vendors

```python
from apps.common.models import SoftDeleteModel, TimeStampedModel, HardDeleteMixin
from apps.common.permissions import IsVendor
from apps.common.events import event_bus

class Vendor(SoftDeleteModel, TimeStampedModel, HardDeleteMixin):
    logo = models.URLField(blank=True, null=True)  # Cloudinary URL

# After verification:
event_bus.emit_on_commit('vendor.verified', vendor_id=str(vendor.pk))
```

### apps/orders

```python
from apps.common.models import SoftDeleteModel, TimeStampedModel
from apps.common.events import event_bus

class Order(SoftDeleteModel, TimeStampedModel): ...

event_bus.emit_on_commit('order.placed', order_id=str(order.pk))
event_bus.emit_on_commit('order.shipped', order_id=str(order.pk), tracking_number=tracking_no)
```

### apps/payments

```python
from apps.common.events import event_bus

event_bus.emit_on_commit('payment.captured', payment_id=str(payment.pk), amount=amount)
event_bus.emit_on_commit('payment.failed', payment_id=str(payment.pk), reason=reason)
```

### apps/inventory

```python
from apps.common.models import SoftDeleteModel, TimeStampedModel

class StockItem(SoftDeleteModel, TimeStampedModel):
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    # Analytics + soft-delete come for free
```

---

## Stress Test Results

Verified 2026-03-16 · 45 tests, 0 failures (exit code 0):

| Test | Result |
|---|---|
| Concurrent first-INSERT race (10 threads) | `total_created=10` ✅ No IntegrityError |
| Concurrent UPDATE race (50 threads) | `total_created=50` ✅ No lost updates |
| Negative delta clamping | `total_active=0` ✅ No negatives |
| Registration duplicate phone | 400 returned (not 500) ✅ Savepoint fix working |
| EventBus subscription at startup | `on_user_registered` subscribed ✅ |
| MemberIDCounter tracking | 0 phantom updates ✅ Exclusion working |
| Admin CSV export | CSV downloaded ✅ No AttributeError |
| Cloudinary presign + webhook (concurrent 100) | All idempotent ✅ |
| Ninja /api/v1/ninja/auth/ URL | 200 OK ✅ Correct namespace |

---
**End of Document** · Last updated 2026-03-16
