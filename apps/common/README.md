# apps/common — Developer Reference

> **Version** 2026-02-27 · **Django** 6.0.2 · **Maintainer** Fashionistar Engineering

This document is the canonical reference for every class, model, mixin, middleware, permission, utility, and component in `fashionistar_backend/apps/common`. 

**This applies to our entire role ecosystem**: Superadmins, Admins, Vendors, Clients, Support, Reviewers/Editors, and Sales/Assistants.

---

## Table of Contents

1. [Overview & Role System](#overview--role-system)
2. [Security & Audit Logging](#security--audit-logging)
3. [Event Message Bus (`events.py`)](#event-message-bus-eventspy)
4. [Middleware](#middleware)
5. [Models](#models)
   - [SoftDeleteModel](#softdeletemodel)
   - [DeletedRecords](#deletedrecords)
   - [DeletionAuditCounter](#deletionauditcounter)
   - [ModelAnalytics](#modelanalytics)
   - [TimeStampModel](#timestampmodel)
   - [HardDeleteMixin](#harddeletemixin)
6. [Managers](#managers)
7. [Permissions](#permissions)
8. [Admin Mixins](#admin-mixins)
9. [Tasks (Celery)](#tasks-celery)
10. [Signals](#signals)
11. [Exceptions](#exceptions)
12. [Renderers](#renderers)
13. [Utilities & Providers](#utilities--providers)

---

## Overview & Role System

`apps.common` is the platform-wide shared infrastructure layer. It underpins security, database integrity, analytics, error handling, and cross-cutting concerns for the modular monolith architecture.

The platform recognizes 7 primary user roles (checked via `getattr(user, 'role', None)` and mapped in `permissions.py`):

1. **Client**: Shoppers and consumers.
2. **Vendor**: Sellers who own stores and list products.
3. **Support**: Customer service representatives.
4. **Reviewer / Editor**: Content moderation and review.
5. **Assistant / Sales**: Sales analytics and marketing.
6. **Admin**: Staff with elevated management rights.
7. **Superadmin**: Full platform access (`is_superuser=True`).

**Golden rule for developers**: Every feature in this app is designed for **high concurrency** and **fire-and-forget** patterns. Do not write synchronous blocking operations here. Use Celery (`transaction.on_commit`) and the `EventBus` for cross-app boundaries.

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

For lifecycle metrics (counting creates/updates/deletes safely at 100K req/s), we use the custom `ModelAnalytics` system (see below).

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
3. **`SecurityAuditMiddleware`**: (See Security & Audit Logging).

---

## Models

### SoftDeleteModel
**File:** `apps/common/models.py`

Abstract base class. Inherit from this instead of `models.Model` for any model that needs soft-delete.
- `is_deleted` (bool), `deleted_at` (datetime).
- Calling `.soft_delete()` sets flags, archives json payload to `DeletedRecords`, and fires async notification tasks.
- Overrides default manager to hide `is_deleted=True` records.

### DeletedRecords
Forensic archive table. One row per soft-deleted record containing a JSON backup snapshot (`data`) of the record when it was removed by a vendor, client, or admin.

### DeletionAuditCounter
Stores numerical tallies of `soft_delete`, `hard_delete`, and `restore` actions grouped by `model_name`. Powers admin visualizations.

### ModelAnalytics
The ultimate global counter. One table row per Django model.
Tracks:
- `total_created` (inserts)
- `total_updated` (all field changes via `post_save` capturing vendor modifications)
- `total_active` (live database size)
- `total_soft_deleted`
- `total_hard_deleted`

**Safe for 100K Req/s**: It uses an atomic F()-expression `UPDATE` pattern combined with an `IntegrityError` retry block in `_adjust()` to completely eliminate deadlock race conditions during heavily concurrent events.

### TimeStampModel
**File:** `apps/common/models.py`

Abstract base. Adds standard `created_at` and `updated_at` properties automatically.

### HardDeleteMixin
**File:** `apps/common/models.py`

Provides a `hard_delete(user)` method. Validates that the caller is the legitimate owner, vendor, or an admin/superadmin prior to executing a permanent `obj.delete()`. It automatically cleans up associated Cloudinary media prior to DB purge.

---

## Managers

**File:** `apps/common/managers/` and `apps/common/models.py`

We supply standard query overriding managers.
- `SoftDeleteManager`: The default manager on `SoftDeleteModel`. Enforces `.filter(is_deleted=False)`.
- `AllObjectsManager`: Available on `SoftDeleteModel` as `.all_objects`. Gives raw unrestricted access including deleted files (essential for restore operations).

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

Provides standard backend admin enhancements.
- `SoftDeleteAdminMixin`: Exposes `.soft_delete_selected()`, `.restore_selected()`, `.hard_delete_selected()` bulk actions to the Django admin panel on any registered model. 
- Implements UI formatting for `colored_active` and `colored_soft_deleted` badge rendering.

---

## Tasks (Celery)

**File:** `apps/common/tasks.py`

Asynchronous Celery tasks executed in the background workers (`RabbitMQ / Redis` brokered).
- `send_account_status_email`: SMTP triggers for restores/deletions.
- `send_account_status_sms`: Twilio text delivery alerts.
- `update_model_analytics_counter`: Safe asynchronous runner for the `ModelAnalytics._adjust()` DB lock operations.
- `keep_service_awake`: Scheduled ping task to keep Render environments warm.

---

## Signals

**File:** `apps/common/signals.py`

Django Signal receivers bound automatically in `apps.py / ready()`.
These capture all application ORM writes to feed `ModelAnalytics`.
- `on_model_created`: Intercepts `post_save(created=True)`.
- `on_model_updated`: Intercepts `post_save(created=False)`. Bypasses state changes where *only* `is_deleted` was updated (to avoid duplicating audit logs from the internal pipeline).
- `on_model_hard_deleted`: Intercepts `post_delete`.

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

- **`apps/common/utils.py`**: Common functions including `delete_cloudinary_asset(public_id)` and random string generators used in test mockups and generic naming routines.
- **`apps/common/providers/`**: Service integration modules (Twilio SMS configurations, proprietary SendGrid / Anymail routing classes, etc).

---

**End of Document**
