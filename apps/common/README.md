# apps/common — Developer Reference

> **Version** 2026-02-27 · **Django** 6.0.2 · **Maintainer** Fashionistar Engineering

This document is the canonical reference for every class, model, mixin, middleware, permission, utility, task, signal, and admin component in `fashionistar_backend/apps/common`. Read it fully before adding or modifying anything in this app.

---

## Table of Contents

1. [Overview & Role System](#overview--role-system)
2. [Architecture Diagram](#architecture-diagram)
3. [Security & Audit Logging](#security--audit-logging)
4. [Event Message Bus (`events.py`)](#event-message-bus-eventspy)
5. [Middleware](#middleware)
6. [Models](#models)
   - [SoftDeleteModel](#softdeletemodel)
   - [DeletedRecords](#deletedrecords)
   - [DeletionAuditCounter](#deletionauditcounter)
   - [ModelAnalytics](#modelanalytics)
   - [TimeStampModel](#timestampmodel)
   - [HardDeleteMixin](#harddeletemixin)
7. [Managers](#managers)
8. [Permissions](#permissions)
9. [Admin Mixins](#admin-mixins)
10. [Tasks (Celery)](#tasks-celery)
11. [Signals](#signals)
12. [Exceptions](#exceptions)
13. [Renderers](#renderers)
14. [Utilities & Providers](#utilities--providers)
15. [Admin Registrations](#admin-registrations)
16. [How to Add a New Model](#how-to-add-a-new-model)
17. [Stress Test Results](#stress-test-results)

---

## Overview & Role System

`apps.common` is the platform-wide shared infrastructure layer. It underpins security, database integrity, analytics, error handling, and cross-cutting concerns for the modular monolith architecture. 

It provides:

| Concern | Solution |
|---|---|
| Soft-delete for any model | `SoftDeleteModel` abstract base |
| Forensic archive of deletes | `DeletedRecords` model |
| Per-action deletion counters | `DeletionAuditCounter` |
| Full lifecycle analytics | `ModelAnalytics` (auto-tracked via signals) |
| Background notifications | Celery tasks via `_fire_and_forget_notification` |
| Race-safe counter writes | F()-first-UPDATE + IntegrityError retry in `_adjust()` |
| Global change auditing | `django-auditlog` (field-level diffs for every model) |
| Security Request Trace | `SecurityAuditMiddleware` logs IP/Role/Method for SIEM |

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
        ├─► post_save(created=True)  ──► ModelAnalytics.record_created()
        ├─► post_save(created=False) ──► ModelAnalytics.record_updated()
        ├─► post_delete              ──► ModelAnalytics.record_hard_deleted()
        │
        ├─► SoftDeleteModel.soft_delete() ──► record_soft_deleted() + notify
        ├─► SoftDeleteModel.restore()     ──► record_restored() + notify
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

Captures the full security footprint of every request across all 7 roles.

- **Client IP**: Extracted securely via `X-Forwarded-For` chain (leftmost real IP).
- **HTTP Context**: Method (GET/POST/PUT), requested URL path, and query string.
- **Trace ID**: `X-Request-ID` attached to all logs for distributed tracing.
- **User Context**: Extracts `user_id` and the explicit user `role` from the request.
- **Device Info**: `User-Agent` and `Referer` headers.
- **Performance**: Wall-clock execution `duration_ms`.
- **Status Classification**:
  - `INFO`: Normal successful traffic (2xx/3xx) `action=REQUEST`.
  - `WARNING`: Permission / Auth failures (401/403) `action=PERMISSION_DENIED`.
  - `ERROR`: Server faults (5xx) `action=SERVER_ERROR`.

Logs are routed to the `security` Python logger, isolating them from application logs so they can directly feed a SIEM or Cloudwatch setup.

### Database Audit Logging

We use `django-auditlog` (`AUDITLOG_INCLUDE_ALL_MODELS=True`) globally across the project to capture raw SQL-level delta changes (old value vs new value) on every vendor and client property modification.

For lifecycle metrics (counting creates/updates/deletes safely at 100K req/s), we use the custom `ModelAnalytics` system (see Models below).

---

## Event Message Bus (`events.py`)

**File:** `apps/common/events.py`

Replaces Django signals for business logic as mandated by back-end architecture goals. 

- **Thread-safe**: Synchronous, in-process event registry safely mapping string keys (e.g. `'user.registered'`) to handler callables.
- **Transaction Safe**: Exposes `event_bus.emit_on_commit(event, **payload)` allowing you to fire an event only after the DB transaction has gracefully committed.
- **Usage**:
  ```python
  from apps.common.events import event_bus

  event_bus.subscribe('order.placed', send_receipt_email)
  event_bus.emit_on_commit('order.placed', order_id=order.id)
  ```

---

## Middleware

**File:** `apps/common/middleware.py`

Registered at the absolute top of the Django `MIDDLEWARE` stack.

1. **`RequestIDMiddleware`**: Injects a `UUID4` onto `request.request_id` and adds the `X-Request-ID` HTTP response header for tracing.
2. **`RequestTimingMiddleware`**: Logs standard application logs with execution times.
3. **`SecurityAuditMiddleware`**: Captures global 7-role requests with X-Forwarded-For IP resolution (See Security & Audit Logging).

---

## Models

### SoftDeleteModel
**File:** `apps/common/models.py`

Abstract base class. Inherit from this instead of `models.Model` for any model that needs soft-delete.

#### Fields

| Field | Type | Description |
|---|---|---|
| `is_deleted` | `BooleanField` | `True` = soft-deleted, hidden from default queries |
| `deleted_at` | `DateTimeField` | Timestamp of last soft-delete (null when active) |

#### Methods

| Method | Description |
|---|---|
| `soft_delete()` | Archives to `DeletedRecords`, sets `is_deleted=True` via `QuerySet.update()` (bypasses `full_clean`), fires `record_soft_deleted` analytics + notification |
| `restore()` | Clears `is_deleted=False` via `all_with_deleted()`, purges `DeletedRecords` entry, fires `record_restored` + notification |
| `_fire_and_forget_notification(action)` | Dispatches email/SMS Celery tasks (fire-and-forget). Actions: `'soft_deleted'`, `'hard_deleted'`, `'restored'` |

#### Default Manager Behaviour

| Manager | Queryset |
|---|---|
| `Model.objects` (default) | **Alive only** (`is_deleted=False`) |
| `Model.objects.all_with_deleted()` | All records including soft-deleted |
| `Model.objects.deleted_only()` | Only soft-deleted |

> [!IMPORTANT]
> Always call `all_with_deleted()` when querying records that may be soft-deleted (e.g., in `restore()`, `hard_delete()`, edit forms for archived users).

#### How to inherit

```python
from apps.common.models import SoftDeleteModel

class Product(SoftDeleteModel):
    name = models.CharField(max_length=200)
    # ... your fields
```

That's it. ModelAnalytics and DeletionAuditCounter are updated automatically via Signals.

---

### DeletedRecords

**File:** `apps/common/models.py`

Forensic archive. One row per soft-deleted record. Created automatically by `SoftDeleteModel.soft_delete()`. Removed automatically by `SoftDeleteModel.restore()`.

#### Fields

| Field | Description |
|---|---|
| `model_name` | Django model class name (`'UnifiedUser'`) |
| `record_id` | PK of the deleted record (string) |
| `deleted_at` | Timestamp of deletion |
| `data` | JSON snapshot of the record at deletion time |

> [!NOTE]
> Deleting a row in the admin `DeletedRecords` view permanently hard-deletes the original source record (cascading purge). Restoring from the view calls the source model's `restore()`.

---

### DeletionAuditCounter

**File:** `apps/common/models.py`

One row per `(model_name, action)` pair. Tracks cumulative totals of `soft_delete`, `hard_delete`, `restore` operations.

| Action | Colour in Admin |
|---|---|
| `soft_delete` | 🟠 Orange |
| `hard_delete` | 🔴 Red |
| `restore` | 🟢 Green |

#### Usage

```python
DeletionAuditCounter.increment(
    model_name='Product',
    action='soft_delete',   # or 'hard_delete' / 'restore'
    count=5,
)
```

Called automatically from `SoftDeleteAdminMixin` bulk actions. Wrap in `try/except` when calling manually — never let it break a user-facing operation.

---

### ModelAnalytics

**File:** `apps/common/models.py`

The heart of the analytics system. **One row per Django model**. Tracks the complete lifecycle of every record across the entire platform.

#### Fields

| Field | Type | Meaning |
|---|---|---|
| `model_name` | `CharField(unique)` | e.g. `'UnifiedUser'` |
| `app_label` | `CharField` | e.g. `'authentication'` |
| `total_created` | `PositiveBigIntegerField` | Cumulative creates. **Never decrements.** |
| `total_active` | `PositiveBigIntegerField` | Currently alive (`is_deleted=False`) |
| `total_updated` | `PositiveBigIntegerField` | Cumulative saves on existing records (vendor/client changes) |
| `total_soft_deleted` | `PositiveBigIntegerField` | Currently soft-deleted (recoverable) |
| `total_hard_deleted` | `PositiveBigIntegerField` | Cumulative permanent purges. **Never decrements.** |

**Identity equation** (always true if no drift):
```
total_created = total_active + total_soft_deleted + total_hard_deleted
```

#### High-level API (call these, not `_adjust`)

```python
ModelAnalytics.record_created(model_name, app_label)
ModelAnalytics.record_updated(model_name, app_label)
ModelAnalytics.record_soft_deleted(model_name, app_label)
ModelAnalytics.record_restored(model_name, app_label)
ModelAnalytics.record_hard_deleted(model_name, app_label, was_soft_deleted=False)
```

Each method calls `_dispatch()` which schedules the write as a fire-and-forget Celery task via `transaction.on_commit()`. **No HTTP request is ever blocked.**

#### `_adjust()` — Race-Safe Counter Mutation

```
Step 1: F()-expression UPDATE (atomic SQL, no lock needed)
Step 2: If 0 rows updated → row doesn't exist → INSERT (create)
Step 3: If IntegrityError on INSERT → another worker won the race
        → retry the UPDATE (which now finds the row)
```

This pattern eliminates the `select_for_update()` deadlock risk and is safe at 100K+ concurrent requests. All counters are clamped to ≥ 0 via `Greatest(F(field) + delta, 0)`.

> [!WARNING]
> Never call `_adjust()` or `_dispatch()` directly from signal handlers or view code. Always use the `record_*` class methods which handle `transaction.on_commit()` wrapping automatically.

---

### TimeStampModel
**File:** `apps/common/models.py`

Abstract base. Adds standard `created_at` and `updated_at` properties automatically across inherited resources.

---

### HardDeleteMixin
**File:** `apps/common/models.py`

Mixin for permanent deletion with permission checks. Inherit alongside `SoftDeleteModel` when a model needs user-controlled hard-delete.

```python
class Product(SoftDeleteModel, HardDeleteMixin):
    ...
```

`hard_delete(user)` checks that the caller is superuser, admin, vendor owner, or the record owner. Fires notification + handles Cloudinary cleanup before the physical SQL DELETE.

---

## Managers

**File:** `apps/common/managers/` and `apps/common/models.py`

| Manager | Usage |
|---|---|
| `SoftDeleteManager` (default) | Filters `is_deleted=False`. Used by `Model.objects`. |
| `AllObjectsManager` | Exposes `.all_with_deleted()` and `.deleted_only()`. Returns raw unrestricted access including deleted records. |

The default manager returns only alive records so existing Django admin/API code never accidentally surfaces soft-deleted data.

---

## Permissions

**File:** `apps/common/permissions.py`

Object-level and view-level authorization classes using DRF's `BasePermission`. Every class acts securely by verifying the user type before validating the explicit request context. Both synchronous `has_permission` and Django async `has_permission_async` are provided for all definitions.

Roles Implemented:
- `IsVendor`: Vendor portals & store management.
- `IsClient`: Frontward customer carts and orders.
- `IsStaff`: Assistant / Admin / Reviewer / Support.
- `IsSupport`: Direct customer support dashboards.
- `IsEditor`: `reviewer` role access for product checks.
- `IsSales`: `assistant` role access.
- `IsOwner`: Resource-level check (`obj.user == request.user`).

Extensive `logging` captures every Anonymous and Unauthorized violation attempt within these classes.

---

## Admin Mixins

**File:** `apps/common/admin_mixins.py`

### `SoftDeleteAdminMixin`

Inherit in any `ModelAdmin` that uses `SoftDeleteModel`:

```python
from apps.common.admin_mixins import SoftDeleteAdminMixin

@admin.register(Product)
class ProductAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    ...
```

Provides:

| Feature | Detail |
|---|---|
| `get_queryset()` | Returns all records (alive + deleted) |
| `_is_deleted_badge()` | Renders 🔴 DELETED / 🟢 ACTIVE badge |
| `soft_delete_selected` action | Bulk soft-delete (single `QuerySet.update()`, notifications per-record) |
| `restore_selected` action | Bulk restore (single `QuerySet.update()`, archive cleanup, notifications) |
| `hard_delete_selected` action | Bulk permanent delete — superusers only |
| `delete_model()` | Single-record delete routes to soft-delete |
| `delete_queryset()` | Routes to soft-delete or hard-delete depending on record state |

> [!IMPORTANT]
> All bulk actions use a **single** `QuerySet.update()` call for performance (100K records handled safely). Notifications fire per-record as fire-and-forget Celery tasks **after** the bulk update.

---

## Tasks (Celery)

**File:** `apps/common/tasks.py`

| Task | Description |
|---|---|
| `keep_service_awake` | Periodic health ping to prevent Render free-tier spin-down |
| `send_account_status_email` | Email user on soft-delete/restore/hard-delete |
| `send_account_status_sms` | SMS user on same events |
| `update_model_analytics_counter` | Background `ModelAnalytics._adjust()` call |

All tasks use `apply_async(retry=False, ignore_result=True)` from signal handlers — true fire-and-forget. If the broker is down, `ModelAnalytics._dispatch()` falls back to a synchronous `_adjust()` call with a `WARNING` log.

---

## Signals

**File:** `apps/common/signals.py` · **Registered in:** `apps/common/apps.py:CommonConfig.ready()`

| Signal | Handler | Counter updated |
|---|---|---|
| `post_save(created=True)` | `on_model_created` | `total_created`, `total_active` |
| `post_save(created=False)` | `on_model_updated` | `total_updated` |
| `post_delete` | `on_model_hard_deleted` | `total_hard_deleted`, `total_active`/`total_soft_deleted` |

**Excluded models** (not tracked):
- Django internals: `Session`, `ContentType`, `Permission`, `LogEntry`
- JWT tokens: `BlacklistedToken`, `OutstandingToken`
- Analytics tables themselves: `ModelAnalytics`, `DeletionAuditCounter`
- Archive: `DeletedRecords`
- Celery Beat schedules

**Smart update filter**: `on_model_updated` skips saves where `update_fields` contains only `{is_deleted, deleted_at}` to avoid double-counting soft-delete pipeline ops.

---

## Exceptions

**File:** `apps/common/exceptions.py`

Contains `custom_exception_handler`. 
When wired into DRF's `EXCEPTION_HANDLER`, this catches all `ValidationError`, `Http404`, `AuthenticationFailed`, and internal Server crashes (500), forcing them into a standardized JSON response envelope:
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

Provides standard JSON payload envelopes on successful `APIView` responses. Formats all endpoint returns cleanly nested beneath a standard parent object interface.

---

## Utilities & Providers

**File:** `apps/common/utils.py` and `apps/common/providers/`

Shared helper functions (e.g., `delete_cloudinary_asset`), random string generators used in test mockups, and proprietary `providers/` service integrations (Twilio SMS configurations, proprietary SendGrid / Anymail routing classes, etc). Import from here rather than duplicating logic in individual apps.

---

## Admin Registrations

**File:** `apps/common/admin.py`

| Admin class | Model | Access |
|---|---|---|
| `DeletedRecordsAdmin` | `DeletedRecords` | Superusers; delete cascades to source record |
| `DeletionAuditCounterAdmin` | `DeletionAuditCounter` | Superadmins only (read-only) |
| `ModelAnalyticsAdmin` | `ModelAnalytics` | Superadmins only (read-only) |

Both analytics admins have all `has_*_permission` methods gated on `request.user.is_superuser`.

---

## How to Add a New Model

### Step 1 — Inherit `SoftDeleteModel`

```python
# apps/yourapp/models.py
from apps.common.models import SoftDeleteModel

class YourModel(SoftDeleteModel):
    name = models.CharField(max_length=200)
    # your fields ...
```

`ModelAnalytics` and `DeletionAuditCounter` rows are created **automatically** on first create/soft-delete. No manual wiring needed.

### Step 2 — Register the ModelAdmin

```python
# apps/yourapp/admin.py
from apps.common.admin_mixins import SoftDeleteAdminMixin

@admin.register(YourModel)
class YourModelAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('name', '_is_deleted_badge', ...)
    actions = ['soft_delete_selected', 'restore_selected', 'hard_delete_selected']
```

### Step 3 — Run migrations

```bash
python manage.py makemigrations yourapp
python manage.py migrate
```

### Step 4 — Verify in admin

- Go to **Common → Model Analytics** — a row for `YourModel` appears after the first save.
- Go to **Common → Deletion Audit Counters** — rows appear after first soft/hard delete.
- Go to **Common → Deleted Records** — entries appear after soft-delete.

### Rules to follow

| ✅ DO | ❌ DON'T |
|---|---|
| Use `Model.objects.all_with_deleted()` when you may need deleted records | Use `Model.objects.filter(is_deleted=True)` (bypasses manager) |
| Wrap `DeletionAuditCounter.increment()` in `try/except` | Let analytics exceptions crash user-facing code |
| Dispatch notifications via `_fire_and_forget_notification()` | Call email/SMS directly from views or signals |
| Use `record_*()` class methods to update ModelAnalytics | Call `_adjust()` directly from signal handlers |
| Use `QuerySet.update()` in bulk admin actions | Loop and call `.save()` per record (N+1) |

---

## Stress Test Results

Verified 2026-02-27 via `python manage.py shell` (5 tests, 0 failures):

| Test | Concurrency | Result |
|---|---|---|
| Concurrent first-INSERT race | 10 threads | `total_created=10` ✅ No IntegrityError |
| Concurrent UPDATE race | 50 threads | `total_created=50` ✅ No lost updates |
| Negative delta clamping | 1 thread, delta=-100 from 2 | `total_active=0` ✅ No negatives |
| `record_updated` isolation | 1 thread, delta=5 | `total_updated=5`, created/active unchanged ✅ |
| Identity equation | Manual set | `created == active + soft + hard` ✅ |

All at SQLite (local dev). On PostgreSQL (production) F()-expressions are fully atomic — the pattern is even safer.

---
**End of Document**
