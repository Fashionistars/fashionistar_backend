# `apps/audit_logs` — Enterprise Audit Logging System

> **Version:** v2.0 — Phase 9 (2026 GDPR / NDPR / PCI-DSS v4 Production Release)
> **Scope:** Structured, immutable, append-only audit trail for the full Fashionistar platform
> **Migration:** Currently at `0006_phase9_compliance_fields`

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [File Structure](#file-structure)
4. [Database Schema & Indexes](#database-schema--indexes)
5. [Model: AuditEventLog](#model-auditeventlog)
6. [Event Types & Categories](#event-types--categories)
7. [AuditService API](#auditservice-api)
8. [Phase 9 Compliance Fields](#phase-9-compliance-fields)
9. [Phase 4 Dispatch Decoupling](#phase-4-dispatch-decoupling)
10. [Middleware: AuditContextMiddleware](#middleware-auditcontextmiddleware)
11. [Celery Task: write_audit_event](#celery-task-write_audit_event)
12. [Retention & Legal Hold](#retention--legal-hold)
13. [Admin Interface](#admin-interface)
14. [Domain-Specific Usage Examples](#domain-specific-usage-examples)
15. [Advanced Queries](#advanced-queries)
16. [Security & Compliance Design](#security--compliance-design)
17. [Troubleshooting](#troubleshooting)

---

## Overview

`apps/audit_logs` is the **enterprise audit backbone** of the Fashionistar platform. Every compliance-critical event — from login attempts and payment processing to admin bulk deletions and KYC verifications — flows through this single system.

### Design Guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| **Immutable** | `save()` guard blocks any UPDATE after creation |
| **Never lost** | Celery + PostgreSQL fallback; broker-down safe |
| **Non-blocking** | All writes are fire-and-forget via `apply_async()` |
| **Tamper-proof** | Admin shows read-only; no delete permission |
| **GDPR Art. 30** | Records of processing activities with `data_subject_id` |
| **PCI-DSS v4 Req. 10** | TLS version, payload sizes, legal hold enforcement |
| **NDPR § 2.1** | Nigerian Data Protection Regulation data security |
| **Legal hold** | `legal_hold=True` rows survive ALL automated deletion paths |

---

## Architecture

```
HTTP Request
    │
    ▼
AuditContextMiddleware (entry)
  • Extracts IP, UA, correlation-id, actor
  • Phase 9: extracts api_version, tls_version,
    session_fingerprint, request_size_bytes
  • Stores in _audit_ctx (contextvars.ContextVar)
    │
    ▼
Django View / DRF Endpoint / Ninja Handler
  • Business logic runs
  • Calls AuditService.log() at key decision points
    │
    ▼
AuditService.log()
  • Resolves actor, IP, UA, geo, session
  • Phase 9: auto-resolves api_version, tls_version,
    data_subject_id
  • Builds payload dict
  • Calls AuditService._dispatch(payload)
    │
    ├─── Celery broker UP → apply_async() → Celery worker
    │                              │
    │                              ▼
    │                    write_audit_event task
    │                      • Background GeoIP enrichment
    │                      • Phase 9: geo_country_code, geo_city
    │                      • AuditEventLog(**payload).save()
    │
    └─── Celery broker DOWN → _write_sync(payload)
                               • Direct DB write (no broker needed)
                               • NEVER drops events
    │
    ▼
AuditContextMiddleware (exit)
  • If response is 4xx/5xx → ASGI: asyncio.get_running_loop().create_task()
                            → WSGI: daemon threading.Thread
  • Never blocks the HTTP response path
```

### ASGI vs WSGI Pattern

```python
# ASGI path (non-blocking, no sync_to_async needed)
loop = asyncio.get_running_loop()
loop.create_task(_async_dispatch_audit(payload))

# WSGI path (daemon thread — does not block gunicorn worker)
t = threading.Thread(target=_sync_dispatch_audit, args=(payload,), daemon=True)
t.start()
```

---

## File Structure

```
apps/audit_logs/
├── __init__.py
├── admin.py                        # AuditEventLogAdmin — read-only, CSV export, Phase 9 fieldsets
├── apps.py                         # AppConfig
├── middleware.py                   # AuditContextMiddleware — dual ASGI/WSGI, Phase 9 extraction
├── mixins.py                       # AuditedModelAdmin — auto-log admin create/update/delete
├── models.py                       # AuditEventLog — 55+ event types, 15 categories, Phase 9 fields
├── services/
│   ├── __init__.py                 # Re-exports AuditService
│   ├── audit.py                    # AuditService.log() — canonical high-level API
│   └── admin_backend.py            # admin_audit helpers (log_admin_action, log_bulk_delete)
├── tasks.py                        # write_audit_event, cleanup_audit_logs Celery tasks
├── management/
│   └── commands/
│       └── purge_audit_logs.py     # Management command with legal_hold guard
├── migrations/
│   ├── 0001_initial_audit_event_log.py
│   ├── 0002_auditeventlog_correlation_id_idx.py
│   ├── 0003_client_context_fields.py
│   ├── 0004_additional_indexes.py
│   ├── 0005_actor_role_session_fields.py
│   └── 0006_phase9_compliance_fields.py  # ← CURRENT: 10 new compliance fields
├── README.md                       # This file
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_services.py
    ├── test_admin.py
    ├── test_middleware.py
    └── test_tasks.py
```

---

## Database Schema & Indexes

### Full AuditEventLog DDL (PostgreSQL 17)

```sql
CREATE TABLE audit_logs_auditeventlog (
    -- ── Identity ─────────────────────────────────────────────────────────
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- ── Event classification ─────────────────────────────────────────────
    event_type          VARCHAR(60) NOT NULL,
    event_category      VARCHAR(60) NOT NULL,
    severity            VARCHAR(20) NOT NULL DEFAULT 'info',
    action              TEXT NOT NULL,

    -- ── Actor snapshot ───────────────────────────────────────────────────
    actor_id            UUID REFERENCES authentication_unifieduser(id) ON DELETE SET NULL,
    actor_email         VARCHAR(254),
    actor_role          VARCHAR(30),
    session_id          VARCHAR(128),

    -- ── Network context ──────────────────────────────────────────────────
    ip_address          INET,
    user_agent          TEXT,
    device_type         VARCHAR(30),
    browser_family      VARCHAR(80),
    os_family           VARCHAR(80),
    country             VARCHAR(100),
    country_code        VARCHAR(10),
    city                VARCHAR(100),
    correlation_id      VARCHAR(64),

    -- ── Resource ─────────────────────────────────────────────────────────
    resource_type       VARCHAR(100),
    resource_id         VARCHAR(255),

    -- ── HTTP context ─────────────────────────────────────────────────────
    request_method      VARCHAR(10),
    request_path        VARCHAR(500),
    response_status     SMALLINT,
    duration_ms         FLOAT,

    -- ── Diff / forensic ──────────────────────────────────────────────────
    old_values          JSONB,
    new_values          JSONB,
    metadata            JSONB,

    -- ── Error ────────────────────────────────────────────────────────────
    error_message       TEXT,

    -- ── Frontend client context (Wave B3) ────────────────────────────────
    client_device_id    VARCHAR(128),
    client_timezone     VARCHAR(64),
    client_locale       VARCHAR(20),
    client_platform     VARCHAR(30),
    client_geo_lat      FLOAT,
    client_geo_lng      FLOAT,
    client_geo_accuracy_m FLOAT,

    -- ── Compliance ───────────────────────────────────────────────────────
    is_compliance       BOOLEAN NOT NULL DEFAULT FALSE,
    retention_days      INTEGER NOT NULL DEFAULT 2555,

    -- ── Phase 9: 2026 GDPR/NDPR/PCI-DSS compliance fields ───────────────
    request_size_bytes  INTEGER,            -- incoming payload size (anomaly detection)
    response_size_bytes INTEGER,            -- outgoing payload size (breach indicator)
    tls_version         VARCHAR(10),        -- 'TLSv1.3', 'TLSv1.2' (PCI-DSS Req.10.3)
    session_fingerprint VARCHAR(64),        -- SHA-256 device fingerprint (fraud detection)
    api_version         VARCHAR(10),        -- 'v1', 'v2' (per-version security analysis)
    tenant_id           UUID,               -- future multi-tenant partition
    legal_hold          BOOLEAN NOT NULL DEFAULT FALSE,  -- PCI freeze, blocks ALL deletion
    data_subject_id     UUID,               -- GDPR Art.15 SAR reference (denormalised)
    geo_country_code    VARCHAR(2),         -- strict ISO 3166-1 alpha-2 (e.g. 'NG','GB')
    geo_city            VARCHAR(100),       -- GeoIP city (separate from legacy `city`)

    -- ── Immutable timestamp ───────────────────────────────────────────────
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Indexes (17 composite, covering all production query patterns)

```sql
-- ── Core time-range ──────────────────────────────────────────────────────
CREATE INDEX idx_ael_created    ON audit_logs_auditeventlog(created_at DESC);

-- ── Actor / authentication ───────────────────────────────────────────────
CREATE INDEX idx_ael_actor      ON audit_logs_auditeventlog(actor_id, created_at DESC);
CREATE INDEX idx_ael_actor_time ON audit_logs_auditeventlog(actor_id, created_at DESC);
CREATE INDEX idx_ael_email      ON audit_logs_auditeventlog(actor_email, created_at DESC);

-- ── Event filtering ───────────────────────────────────────────────────────
CREATE INDEX idx_ael_etype      ON audit_logs_auditeventlog(event_type, created_at DESC);
CREATE INDEX idx_ael_ecat       ON audit_logs_auditeventlog(event_category, created_at DESC);

-- ── Security dashboard ───────────────────────────────────────────────────
CREATE INDEX idx_ael_sev        ON audit_logs_auditeventlog(severity, created_at DESC);
CREATE INDEX idx_ael_ip         ON audit_logs_auditeventlog(ip_address, created_at DESC);

-- ── Resource audit trail ─────────────────────────────────────────────────
CREATE INDEX idx_ael_resource   ON audit_logs_auditeventlog(resource_type, resource_id);

-- ── Compliance reports ───────────────────────────────────────────────────
CREATE INDEX idx_ael_compliance ON audit_logs_auditeventlog(is_compliance, created_at DESC);

-- ── Distributed tracing ──────────────────────────────────────────────────
CREATE INDEX idx_ael_corr       ON audit_logs_auditeventlog(correlation_id);

-- ── Geo segmentation ─────────────────────────────────────────────────────
CREATE INDEX idx_ael_country    ON audit_logs_auditeventlog(country, created_at DESC);

-- ── Phase 9 compliance indexes (migration 0006) ──────────────────────────
CREATE INDEX idx_ael_data_subject ON audit_logs_auditeventlog(data_subject_id, created_at DESC);
CREATE INDEX idx_ael_legal_hold   ON audit_logs_auditeventlog(legal_hold, created_at DESC);
CREATE INDEX idx_ael_tenant       ON audit_logs_auditeventlog(tenant_id, created_at DESC);
CREATE INDEX idx_ael_sess_fp      ON audit_logs_auditeventlog(session_fingerprint, created_at DESC);
CREATE INDEX idx_ael_api_actor    ON audit_logs_auditeventlog(api_version, actor_email);
```

---

## Model: AuditEventLog

### Immutability Guard

```python
# models.py — AuditEventLog.save()
def save(self, *args, **kwargs):
    """Enforce append-only semantics — block all UPDATE attempts."""
    if not self._state.adding:
        raise PermissionError(
            "AuditEventLog is immutable. "
            "Records cannot be updated after creation. "
            "(PCI-DSS v4 Req. 10.5.2: audit records must be protected from modification)"
        )
    super().save(*args, **kwargs)
```

### Field Groups

**Core Classification:**
- `event_type` — one of 55+ `EventType` constants
- `event_category` — one of 15 `EventCategory` values
- `severity` — `debug` | `info` | `warning` | `error` | `critical`
- `action` — human-readable description

**Actor Snapshot:**
- `actor` — FK to `UnifiedUser` (`SET NULL` on hard-delete)
- `actor_email` — denormalised (survives user deletion)
- `actor_role` — role at event time (`client`, `vendor`, `admin`)
- `session_id` — JWT `jti` or Django session key

**Network Context:**
- `ip_address`, `user_agent`, `device_type`, `browser_family`, `os_family`
- `country`, `country_code`, `city` — legacy GeoIP fields
- `correlation_id` — request trace ID

**Phase 9 Fields** — see [Phase 9 section](#phase-9-compliance-fields).

---

## Event Types & Categories

### EventType (55+ constants)

```python
class EventType(models.TextChoices):
    # Authentication
    LOGIN_SUCCESS       = "login_success"
    LOGIN_FAILED        = "login_failed"
    LOGOUT              = "logout"
    TOKEN_REFRESH       = "token_refresh"
    PASSWORD_RESET      = "password_reset"
    PASSWORD_CHANGED    = "password_changed"
    EMAIL_VERIFIED      = "email_verified"
    MFA_ENABLED         = "mfa_enabled"
    MFA_DISABLED        = "mfa_disabled"
    FAILED_LOGINS_EXCEEDED = "failed_logins_exceeded"
    ACCOUNT_LOCKED      = "account_locked"
    ACCOUNT_UNLOCKED    = "account_unlocked"
    ACCOUNT_RESTORED    = "account_restored"
    SESSION_EXPIRED     = "session_expired"
    SUSPICIOUS_LOGIN    = "suspicious_login"

    # Payment & Financial
    PAYMENT_SUCCESS     = "payment_success"
    PAYMENT_FAILED      = "payment_failed"
    PAYMENT_INITIATED   = "payment_initiated"
    REFUND_INITIATED    = "refund_initiated"
    REFUND_SUCCESS      = "refund_success"
    REFUND_FAILED       = "refund_failed"
    PAYOUT_INITIATED    = "payout_initiated"
    PAYOUT_SUCCESS      = "payout_success"
    PAYOUT_FAILED       = "payout_failed"
    WALLET_FUNDED       = "wallet_funded"
    WALLET_DEBITED      = "wallet_debited"
    CHARGEBACK          = "chargeback"
    DISPUTE_OPENED      = "dispute_opened"

    # User Management
    USER_REGISTERED     = "user_registered"
    USER_UPDATED        = "user_updated"
    USER_DELETED        = "user_deleted"
    USER_SUSPENDED      = "user_suspended"
    USER_RESTORED       = "user_restored"
    ROLE_CHANGED        = "role_changed"
    PERMISSION_CHANGED  = "permission_changed"

    # KYC
    KYC_SUBMITTED       = "kyc_submitted"
    KYC_APPROVED        = "kyc_approved"
    KYC_REJECTED        = "kyc_rejected"
    KYC_EXPIRED         = "kyc_expired"

    # Orders
    ORDER_PLACED        = "order_placed"
    ORDER_CONFIRMED     = "order_confirmed"
    ORDER_CANCELLED     = "order_cancelled"
    ORDER_COMPLETED     = "order_completed"

    # Admin
    ADMIN_ACTION        = "admin_action"
    SOFT_DELETE         = "soft_delete"
    HARD_DELETE         = "hard_delete"

    # System
    SYSTEM_ERROR        = "system_error"
    SYSTEM_WARNING      = "system_warning"
    API_CALL            = "api_call"
    CONFIG_CHANGED      = "config_changed"
    DATA_EXPORT         = "data_export"
```

### EventCategory (15 categories)

```python
class EventCategory(models.TextChoices):
    AUTHENTICATION    = "authentication"
    PAYMENT           = "payment"
    FINANCIAL         = "financial"
    USER_MANAGEMENT   = "user_management"
    ADMIN             = "admin"
    SECURITY          = "security"
    DATA_MODIFICATION = "data_modification"
    KYC               = "kyc"
    ORDER             = "order"
    NOTIFICATION      = "notification"
    SYSTEM            = "system"
    PRODUCT           = "product"
    CATALOG           = "catalog"
    MEASUREMENT       = "measurement"
    COMPLIANCE        = "compliance"
```

---

## AuditService API

### Basic Usage

```python
from apps.audit_logs.services import AuditService
from apps.audit_logs.models import EventType, EventCategory

# ── Minimal call ─────────────────────────────────────────────────────────
AuditService.log(
    event_type=EventType.LOGIN_SUCCESS,
    event_category=EventCategory.AUTHENTICATION,
    action="User logged in via email OTP",
    actor=request.user,
    request=request,     # ← auto-extracts IP, UA, path, method
)

# ── With compliance flags ─────────────────────────────────────────────────
AuditService.log(
    event_type=EventType.PAYMENT_SUCCESS,
    event_category=EventCategory.PAYMENT,
    action=f"Payment ₦50,000 processed for Order #{order.id}",
    actor=request.user,
    request=request,
    resource_type="Order",
    resource_id=str(order.pk),
    metadata={"reference": "PAY-REF-12345", "gateway": "paystack"},
    is_compliance=True,      # ← 7-year retention, data_subject_id auto-set
    retention_days=2555,
)

# ── With diff (before/after snapshot) ────────────────────────────────────
AuditService.log(
    event_type=EventType.USER_UPDATED,
    event_category=EventCategory.USER_MANAGEMENT,
    action="User email updated",
    actor=admin_user,
    request=request,
    resource_type="UnifiedUser",
    resource_id=str(target_user.pk),
    old_values={"email": "old@example.com"},
    new_values={"email": "new@example.com"},
)
```

### Full Signature (v2.0)

```python
AuditService.log(
    # ── Required ───────────────────────────────────────────────────────────
    event_type: str,            # EventType constant
    event_category: str,        # EventCategory constant
    action: str,                # Human-readable description

    # ── Actor ──────────────────────────────────────────────────────────────
    actor=None,                 # UnifiedUser instance or None
    actor_email: str | None,    # Auto-resolved from actor if not given
    actor_role: str | None,     # Auto-resolved from actor.user_type
    session_id: str | None,     # JWT jti or session key

    # ── Request context (auto-filled when request= given) ─────────────────
    request=None,               # Django HttpRequest — auto-extracts everything
    ip_address: str | None,     # Override IP (takes priority over X-Forwarded-For)
    user_agent: str | None,
    device_type: str | None,    # 'mobile' | 'tablet' | 'desktop' | 'bot'
    browser_family: str | None,
    os_family: str | None,
    request_method: str | None,
    request_path: str | None,
    response_status: int | None,
    duration_ms: float | None,

    # ── Geo (auto-resolved from IP via Redis-cached GeoIP) ─────────────────
    country: str | None,
    country_code: str | None,
    city: str | None,

    # ── Resource ───────────────────────────────────────────────────────────
    resource_type: str | None,  # e.g. 'Order', 'WalletLedgerEntry'
    resource_id: str | None,    # Model PK (coerced to str)

    # ── Diff / forensic ────────────────────────────────────────────────────
    old_values: dict | None,
    new_values: dict | None,
    metadata: dict | None,
    error_message: str | None,
    severity: str = "info",

    # ── Compliance ──────────────────────────────────────────────────────────
    is_compliance: bool = False,
    retention_days: int = 2555,

    # ── Frontend client context (X-Client-* headers) ──────────────────────
    client_device_id: str | None,
    client_timezone: str | None,
    client_locale: str | None,
    client_platform: str | None,
    client_geo_lat: float | None,
    client_geo_lng: float | None,
    client_geo_accuracy_m: float | None,

    # ── Phase 9: 2026 GDPR/NDPR/PCI-DSS compliance fields ─────────────────
    request_size_bytes: int | None,     # Manual: caller passes CONTENT_LENGTH
    response_size_bytes: int | None,    # Manual: middleware extracts Content-Length
    tls_version: str | None,            # Auto: from SSL_PROTOCOL / X-Forwarded-Proto-Version
    session_fingerprint: str | None,    # Auto: from X-Session-Fingerprint header
    api_version: str | None,            # Auto: extracted from /v1/ in request_path
    tenant_id=None,                     # Manual: UUID or str
    legal_hold: bool = False,           # Manual: set by superuser for regulatory freeze
    data_subject_id=None,               # Auto: actor.pk when is_compliance=True
    geo_country_code: str | None,       # Auto: set in Celery worker GeoIP task
    geo_city: str | None,               # Auto: set in Celery worker GeoIP task
) -> None
```

**Key Design Properties:**
- Returns `None`, never raises — all exceptions caught and logged at `WARNING`
- Thread-safe, async-safe (stateless class methods)
- All `None`-safe — every field has a sensible default or auto-resolution path

---

## Phase 9 Compliance Fields

Phase 9 adds 10 new fields to `AuditEventLog` to satisfy the **2026 regulatory compliance framework** (GDPR Art. 30, NDPR § 2.1, PCI-DSS v4 Req. 10).

| Field | Type | Auto-Populated? | Compliance Requirement |
|-------|------|-----------------|------------------------|
| `request_size_bytes` | `PositiveIntegerField` | Middleware (CONTENT_LENGTH) | PCI-DSS anomaly detection |
| `response_size_bytes` | `PositiveIntegerField` | Middleware (Content-Length header) | GDPR breach indicator |
| `tls_version` | `CharField(10)` | `SSL_PROTOCOL` Nginx var | PCI-DSS v4 Req. 10.3 |
| `session_fingerprint` | `CharField(64)` | `X-Session-Fingerprint` header | Fraud detection (no raw PII) |
| `api_version` | `CharField(10)` | Regex from request path | Per-version security analysis |
| `tenant_id` | `UUIDField` | Manual (future multi-tenant) | Multi-tenant data isolation |
| `legal_hold` | `BooleanField` | Manual (superuser admin) | PCI-DSS Req. 10.5 freeze |
| `data_subject_id` | `UUIDField` | `actor.pk` when `is_compliance=True` | GDPR Art. 15 SAR, Art. 17 erasure |
| `geo_country_code` | `CharField(2)` | Celery GeoIP (ISO 3166-1 alpha-2) | PCI-DSS geographic segmentation |
| `geo_city` | `CharField(100)` | Celery GeoIP | Geographic compliance reporting |

### Auto-Resolution Flow

```
HTTP Request arrives
    │
    ▼
AuditContextMiddleware._build_context()
  ├── api_version = _extract_api_version(request.path)  # regex /v(\d+)/
  ├── tls_version = request.META.get("SSL_PROTOCOL")     # Nginx sets this
  ├── session_fingerprint = request.META.get("HTTP_X_SESSION_FINGERPRINT")
  └── request_size_bytes = int(request.META.get("CONTENT_LENGTH", 0))

    │
    ▼
AuditService.log()
  ├── data_subject_id = actor.pk  (only when is_compliance=True)
  └── geo_country_code: left empty here (populated by Celery task)

    │
    ▼
write_audit_event Celery task
  ├── GeoIP enrichment (allow_network=True)
  ├── geo_country_code = raw_cc[:2].upper()   # strict 2-char ISO 3166-1
  └── geo_city = geo.get("city")
```

### Legal Hold Enforcement (Triple Guard)

`legal_hold=True` rows are protected at **three** independent levels:

```python
# 1. Celery cleanup task (tasks.py)
AuditEventLog.objects.filter(
    is_compliance=False,
    retention_days__gt=0,
    legal_hold=False,     # ← Guard 1
).annotate(...).filter(expiry_at__lt=now)...

# 2. Celery cleanup batch delete (tasks.py)
AuditEventLog.objects.filter(
    id__in=expired_ids,
    is_compliance=False,
    legal_hold=False,     # ← Guard 2 (triple-check)
).delete()

# 3. Management command (purge_audit_logs.py)
qs.filter(is_compliance=False, legal_hold=False)  # ← Guard 3
qs.model.objects.filter(id__in=batch_ids, legal_hold=False).delete()
```

---

## Phase 4 Dispatch Decoupling

**Before Phase 4:** Audit side-effects (DeletionAuditCounter, notifications, audit trail) ran inline in the admin action handlers, blocking the HTTP response by N DB writes + N Redis writes per record.

**After Phase 4:** ALL side-effects are deferred to `transaction.on_commit()` callbacks:

```python
# apps/common/admin_mixins.py — soft_delete_selected (Phase 4)
def _post_commit_side_effects(...):
    """Runs after the UPDATE transaction commits. Never blocks the admin page."""
    # 3a. UnifiedUser lifecycle registry → Celery apply_async()
    # 3b. DeletionAuditCounter.increment()
    # 3c. write_audit_event.apply_async()

transaction.on_commit(_post_commit_side_effects)

# apps/common/admin_mixins.py — restore_selected (RC-5 fix)
def _restore_post_commit(...):
    """Runs after the UPDATE transaction commits. Never blocks the admin page."""
    # 3a. upsert_user_lifecycle_registry → Celery
    # 3b. DeletionAuditCounter.increment()
    # 3c. write_audit_event.apply_async()

transaction.on_commit(_restore_post_commit)
```

**Performance impact:** 100-record bulk action went from `~500ms` (100 DB writes blocking the response) to `<5ms` (single UPDATE + deferred side-effects).

---

## Middleware: AuditContextMiddleware

**File:** [`middleware.py`](./middleware.py)

```python
MIDDLEWARE = [
    ...
    "apps.audit_logs.middleware.AuditContextMiddleware",
    ...
]
```

### What it captures

| Context Key | Source | Phase |
|-------------|--------|-------|
| `ip_address` | `X-Forwarded-For` → `REMOTE_ADDR` | Original |
| `user_agent` | `HTTP_USER_AGENT` | Original |
| `correlation_id` | `X-Correlation-ID` or generated UUID4 | Original |
| `actor` | `request.user` (if authenticated) | Original |
| `client_device_id` | `X-Device-ID` header | Wave B3 |
| `client_timezone` | `X-Client-Timezone` header | Wave B3 |
| `client_locale` | `X-Client-Locale` header | Wave B3 |
| `client_platform` | `X-Client-Platform` header | Wave B3 |
| `client_geo_lat/lng` | `X-Client-Geo-Lat/Lng` headers | Wave B3 |
| `session_fingerprint` | `X-Session-Fingerprint` header | Phase 9 |
| `tls_version` | `SSL_PROTOCOL` / `X-Forwarded-Proto-Version` | Phase 9 |
| `api_version` | regex `/v(\d+)/` on `request.path` | Phase 9 |
| `request_size_bytes` | `CONTENT_LENGTH` header | Phase 9 |

### Auto-capture for 4xx / 5xx

The middleware automatically creates audit events for failed HTTP responses (401, 403, 404, 5xx) without any caller action. The auto-capture payload now includes all Phase 9 fields.

### ASGI Deprecation Fix

The middleware was updated to use the non-deprecated pattern:

```python
# Before (deprecated in Python 3.10+):
asyncio.get_event_loop().create_task(...)

# After (correct):
loop = asyncio.get_running_loop()
loop.create_task(_async_dispatch_audit(payload))
```

---

## Celery Task: write_audit_event

**File:** [`tasks.py`](./tasks.py)

```python
@shared_task(name="write_audit_event", bind=True, max_retries=2, default_retry_delay=5)
def write_audit_event(self, payload: dict) -> None:
    ...
```

### `_KNOWN_FIELDS` allowlist

The task strips any unknown payload keys via an allowlist to prevent `TypeError: unexpected keyword argument` when the model evolves. The allowlist now includes all Phase 9 fields:

```python
_KNOWN_FIELDS = {
    # Core fields (original)
    "event_type", "event_category", "severity", "action",
    "actor", "actor_email", "actor_role", "session_id",
    "ip_address", "user_agent", "device_type",
    "browser_family", "os_family",
    "country", "country_code", "city", "correlation_id",
    "resource_type", "resource_id",
    "request_method", "request_path", "response_status", "duration_ms",
    "old_values", "new_values", "metadata", "error_message",
    "is_compliance", "retention_days",
    # Wave B3: client context fields
    "client_device_id", "client_timezone", "client_locale", "client_platform",
    "client_geo_lat", "client_geo_lng", "client_geo_accuracy_m",
    # Phase 9: 2026 compliance fields
    "request_size_bytes", "response_size_bytes", "tls_version",
    "session_fingerprint", "api_version", "tenant_id",
    "legal_hold", "data_subject_id", "geo_country_code", "geo_city",
}
```

### Background GeoIP Enrichment

The task performs full GeoIP resolution (with network calls allowed) in the Celery worker process, keeping the HTTP request path zero-latency:

```python
geo = _resolve_geo(ip_address, allow_network=True)
if geo:
    payload["country"]      = geo.get("country") or ""
    payload["country_code"] = geo.get("country_code") or ""
    payload["city"]         = geo.get("city") or ""
    # Phase 9: strict 2-char ISO 3166-1 alpha-2
    raw_cc = geo.get("country_code") or ""
    payload.setdefault("geo_country_code", raw_cc[:2].upper() or None)
    payload.setdefault("geo_city", geo.get("city") or None)
```

### Cleanup Task

```python
@shared_task(name="audit_log_cleanup", bind=True, max_retries=1)
def cleanup_audit_logs(self) -> dict:
    """Daily cleanup respecting per-row retention_days.
    
    Never deletes:
    - is_compliance=True rows
    - legal_hold=True rows (Phase 9 triple-guard)
    - retention_days <= 0 (permanent)
    """
```

---

## Retention & Legal Hold

### Retention Matrix

| Event Type | `is_compliance` | `retention_days` | Deletable? |
|-----------|-----------------|------------------|------------|
| Financial / Payment | `True` | 2555 (7 years) | ❌ Never |
| KYC / Regulatory | `True` | 2555 (7 years) | ❌ Never |
| Legal Hold | Any | Any | ❌ Never (`legal_hold=True`) |
| Security events | `False` | 730 (2 years) | ✅ After 2 years |
| Auth / Login | `False` | 365 (1 year) | ✅ After 1 year |
| Debug / System | `False` | 90 (3 months) | ✅ After 90 days |

### Setting Legal Hold (Django Admin)

```python
# In Django Admin → Audit Event Logs → [select row]
# Scroll to "2026 Compliance (Phase 9)" fieldset
# legal_hold = True
# ✅ This row will NEVER be deleted by ANY automated process
```

### GDPR Subject Access Request (SAR) — Art. 15

```python
# Find all events linked to a specific data subject
# Works even if the user has been hard-deleted (denormalised UUID)
from apps.audit_logs.models import AuditEventLog
import uuid

subject_id = uuid.UUID("user-pk-here")

# New Phase 9 query (survives user deletion)
events = AuditEventLog.objects.filter(
    data_subject_id=subject_id,
).order_by("created_at")

# Legacy query (works while user exists)
events = AuditEventLog.objects.filter(
    actor_email="user@example.com",
).order_by("created_at")
```

### Management Command

```bash
# Preview what would be deleted (dry-run)
python manage.py purge_audit_logs --dry-run

# Delete expired non-compliance rows older than 90 days
python manage.py purge_audit_logs --older-than 90

# Include compliance rows (requires --force for production)
python manage.py purge_audit_logs --include-compliance --force

# Note: legal_hold=True rows are ALWAYS excluded regardless of flags
```

---

## Admin Interface

**File:** [`admin.py`](./admin.py)

### Access

- URL: `/admin/audit_logs/auditeventlog/`
- Requires: superuser or staff with `view` permission

### Features

| Feature | Description |
|---------|-------------|
| **Read-only** | No add/change/delete permissions — immutable audit trail |
| **CSV Export** | `export_compliance_csv` action — streams all fields including Phase 9 |
| **Advanced search** | By IP, email, correlation ID, resource ID |
| **Filters** | Severity, event type, category, is_compliance, `legal_hold`, `api_version`, country |
| **Phase 9 Fieldset** | Collapsible "2026 Compliance (Phase 9)" section in detail view |
| **Pagination** | 50 rows per page for performance |

### Phase 9 Admin Fieldset

The detail view now includes a collapsible **"2026 Compliance (Phase 9 — GDPR/NDPR/PCI-DSS)"** section showing all 10 new compliance fields:

```
▼ 2026 Compliance (Phase 9 — GDPR/NDPR/PCI-DSS)
  Request size: 2,048 bytes
  Response size: 15,360 bytes
  TLS version: TLSv1.3
  Session fingerprint: a3f8d2...
  API version: v2
  Tenant ID: —
  Legal hold: No
  Data subject ID: 550e8400-e29b-41d4-a716-446655440000
  Geo country code: NG
  Geo city: Lagos
```

---

## Domain-Specific Usage Examples

### Authentication App

```python
# apps/authentication/services/auth_service.py

from apps.audit_logs.services import AuditService
from apps.audit_logs.models import EventType, EventCategory

def login_user(request, user, method="email_otp"):
    AuditService.log(
        event_type=EventType.LOGIN_SUCCESS,
        event_category=EventCategory.AUTHENTICATION,
        action=f"Login successful via {method}",
        actor=user,
        request=request,
        metadata={"method": method},
    )

def login_failed(request, email, reason):
    AuditService.log(
        event_type=EventType.LOGIN_FAILED,
        event_category=EventCategory.AUTHENTICATION,
        action=f"Login failed for {email}: {reason}",
        severity="warning",
        request=request,
        actor_email=email,
        error_message=reason,
    )
```

### Payment Webhook Handler

```python
# apps/payments/webhooks/paystack.py

def handle_paystack_charge_success(payload, request=None):
    reference = payload["reference"]
    amount_kobo = payload["amount"]
    order = Order.objects.get(external_reference=reference)
    order.mark_paid()

    AuditService.log(
        event_type=EventType.PAYMENT_SUCCESS,
        event_category=EventCategory.PAYMENT,
        action=f"Payment ₦{amount_kobo / 100:,.2f} confirmed via Paystack",
        resource_type="Order",
        resource_id=str(order.pk),
        metadata={
            "reference": reference,
            "amount_kobo": amount_kobo,
            "gateway": "paystack",
            "channel": payload.get("channel"),
        },
        is_compliance=True,  # ← PCI-DSS Level 1
        # data_subject_id auto-set from actor.pk since is_compliance=True
    )
```

### Admin Bulk Delete (with transaction.on_commit)

```python
# This is already implemented in apps/common/admin_mixins.py
# soft_delete_selected and restore_selected both use transaction.on_commit()
# The audit event fires AFTER the DB transaction commits — non-blocking.

# Example from your own admin:
with transaction.atomic():
    queryset.filter(pk__in=pks).update(is_deleted=True, deleted_at=now)

def _post_commit():
    write_audit_event.apply_async(kwargs={"payload": {...}})

transaction.on_commit(_post_commit)
```

### KYC Verification

```python
# Inside compliance-grade KYC approval flow

def approve_kyc(kyc_submission, reviewer, request):
    kyc_submission.approve()

    AuditService.log(
        event_type=EventType.KYC_APPROVED,
        event_category=EventCategory.KYC,
        action=f"KYC approved for {kyc_submission.user.email}",
        actor=reviewer,
        request=request,
        resource_type="KYCSubmission",
        resource_id=str(kyc_submission.pk),
        is_compliance=True,
        retention_days=2555,  # 7 years (CBN / NDPR requirement)
        # data_subject_id auto-set to kyc_submission.user.pk
    )
```

---

## Advanced Queries

### GDPR Subject Access Request (Phase 9)

```python
# Uses denormalised data_subject_id — works even after user deletion
from apps.audit_logs.models import AuditEventLog
import uuid

subject_id = uuid.UUID("user-pk-uuid-here")
events = AuditEventLog.objects.filter(
    data_subject_id=subject_id,
).order_by("created_at").values(
    "created_at", "event_type", "action",
    "ip_address", "country", "geo_city",
    "api_version", "tls_version",
)
```

### Detect TLS Downgrade Attacks (Phase 9)

```python
# Flag any request that used TLS 1.2 or below
downgrade_events = AuditEventLog.objects.filter(
    tls_version__in=["TLSv1.2", "TLSv1.1", "TLSv1"],
    created_at__gte=timezone.now() - timedelta(days=7),
).order_by("-created_at")
```

### Per-API-Version Security Analysis (Phase 9)

```python
# Count auth failures by API version
from django.db.models import Count
AuditEventLog.objects.filter(
    event_type=EventType.LOGIN_FAILED,
    created_at__gte=timezone.now() - timedelta(days=30),
).values("api_version").annotate(fail_count=Count("id")).order_by("-fail_count")
```

### Session Fingerprint Cross-Correlation (Phase 9)

```python
# Find all events sharing a fingerprint across different user accounts
fingerprint = "a3f8d2b1..."  # from fraud alert
suspicious = AuditEventLog.objects.filter(
    session_fingerprint=fingerprint,
).values("actor_email", "ip_address", "event_type").distinct()
# → Reveals credential stuffing / account takeover using same device
```

### Find Legal-Hold Rows

```python
frozen_rows = AuditEventLog.objects.filter(
    legal_hold=True,
).order_by("-created_at")
print(f"{frozen_rows.count()} rows under legal hold — will never be deleted")
```

### Compliance Report Export

```python
import csv
from apps.audit_logs.models import AuditEventLog

def export_pci_compliance_report(output_file, start_date, end_date):
    """Export PCI-DSS compliance report for a date range."""
    qs = AuditEventLog.objects.filter(
        is_compliance=True,
        created_at__range=(start_date, end_date),
    ).values(
        "id", "created_at", "event_type", "actor_email",
        "ip_address", "geo_country_code", "geo_city",
        "tls_version", "api_version", "request_size_bytes",
        "response_size_bytes", "resource_type", "resource_id",
        "legal_hold", "data_subject_id",
    ).order_by("created_at")

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(qs[0].keys()))
        writer.writeheader()
        for row in qs.iterator(chunk_size=500):
            writer.writerow(row)
```

---

## Security & Compliance Design

### Immutability Chain

```
1. Model save() guard → raises PermissionError on any UPDATE
2. Admin → ReadOnlyAdminMixin → has_change_permission = False
3. DRF → no update endpoint exists for AuditEventLog
4. Ninja → no mutation schema defined
5. Database → no application-level user has UPDATE on audit table (recommended)
```

### Data Redaction

Sensitive fields are automatically replaced with `***REDACTED***` in `old_values` / `new_values` diffs:

```python
_REDACTED_FIELDS = frozenset({
    "password", "api_secret", "secret_key", "token",
    "otp_secret", "otp_base32", "private_key",
})

# Also redacts any key containing "password" or "secret"
```

### GeoIP Caching (Performance)

```
First call for IP 197.210.1.1:
  → Cache miss → HTTP call to IPinfo API (1.5s timeout)
  → Result cached in Redis for 24 hours

Subsequent calls:
  → Cache hit → 0ms (Redis GET)
  → No external HTTP call
```

### Compliance Regulatory Coverage

| Regulation | Coverage |
|-----------|----------|
| **GDPR Art. 15** | SAR via `data_subject_id` (survives user deletion) |
| **GDPR Art. 17** | Erasure exemption: `is_compliance=True` rows retained |
| **GDPR Art. 30** | Records of processing activities — every audit row |
| **NDPR § 2.1** | Data security obligations — immutable, encrypted transit |
| **PCI-DSS v4 Req. 10.2** | Audit log events generated for all access |
| **PCI-DSS v4 Req. 10.3** | TLS version captured per request |
| **PCI-DSS v4 Req. 10.5** | `legal_hold` prevents modification/deletion |
| **CBN KYC** | 7-year retention for KYC/AML compliance events |

---

## Troubleshooting

### Q: Events not being logged?

1. Check middleware registration:
```python
# settings/base.py
MIDDLEWARE = [
    ...
    "apps.audit_logs.middleware.AuditContextMiddleware",
    ...
]
```

2. Check Celery broker:
```bash
redis-cli PING  # Should return PONG
celery -A backend worker -l info
```

3. Check for broker-fallback mode:
```bash
# If broker is down, audit writes go directly to DB via _write_sync()
grep "AuditService._write_sync" logs/django.log
```

### Q: Phase 9 fields are all NULL?

**`tls_version`:** Requires Nginx `ssl_protocol` configuration:
```nginx
# nginx.conf
uwsgi_param SSL_PROTOCOL $ssl_protocol;
# or for gunicorn:
proxy_set_header X-Forwarded-Proto-Version $ssl_protocol;
```

**`session_fingerprint`:** Requires frontend to send the `X-Session-Fingerprint` header:
```typescript
// frontend/lib/audit-headers.ts
const fingerprint = await computeSessionFingerprint(); // SHA-256 of UA+lang+tz+screen
headers["X-Session-Fingerprint"] = fingerprint;
```

**`geo_country_code` / `geo_city`:** Populated in Celery task. Check worker is running.

### Q: Can I delete audit logs?

**No.** By design:
- Application: no `delete()` endpoint
- Admin: `ReadOnlyAdminMixin` removes delete permission
- `legal_hold=True`: survives all automated deletion paths
- `is_compliance=True`: never touched by cleanup tasks

### Q: How do I perform a GDPR erasure (Right to Be Forgotten)?

Compliance-grade approach:
1. Set `actor_email` = `"***REDACTED***"` (manual DB operation by DPO only)
2. `data_subject_id` is retained (UUID, not PII) for SAR reference
3. `actor_id` FK → `NULL` (already happens on hard-delete of UnifiedUser)
4. Audit events themselves are retained (GDPR Art. 17(3)(b) — legal obligation)

---

**Last updated:** 2026-05-30 · **Phase:** v2.0 Phase 9 · **Maintainer:** Fashionistar Engineering
