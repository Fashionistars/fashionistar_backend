# `apps/client/selectors/` — Client Domain Selectors

> **Version:** v2.0 — Phase 8 (asyncio.gather() parallelism)  
> **Last Updated:** 2026-05-30  
> **Architecture Tier:** Selector Layer (read-only data fetching)  
> **Stack:** Django 6.0 LTS · Python 3.12+ · Native async ORM · ZERO `sync_to_async`

---

## Overview

This directory contains the **selector layer** for the `client` domain.
Selectors are pure read-only functions that fetch data from the database
and return it to Django-Ninja async views or DRF sync views.

### Architecture Rules (NON-NEGOTIABLE)

| Rule | Rationale |
|------|-----------|
| Selectors **NEVER mutate data** | Mutations live in `services/` only |
| Sync selectors (no prefix) | Used by DRF sync views, Django admin, management commands |
| Async selectors (prefix `a`) | Used by Django-Ninja async views only |
| **ZERO `sync_to_async()`** | Native Django 6.0 async ORM terminals cover all cases |
| **ZERO `threading.local()`** | Context propagation via `ContextVar` (ASGI-safe) |
| `asyncio.gather()` for independent awaits | Phase 8: concurrent DB calls instead of sequential |

---

## File Structure

```
apps/client/selectors/
├── __init__.py
└── client_selectors.py     ← all sync + async selectors
```

---

## Reverse FK / Related-Name Traversal Map

| Traversal | Target |
|-----------|--------|
| `user.client_profile` | `ClientProfile` (OneToOne) |
| `user.user_orders` | `Order` rows (related_name) |
| `user.cart` | `Cart` (OneToOne, get_or_create) |
| `profile.client_addresses` | `ClientAddress` rows (related_name=`"addresses"`) |
| `ProductWishlist.filter(user=user)` | Wishlist rows for this user |
| `profile.client_measurement_profiles` | Measurement rows (related_name) |

---

## Sync Selectors (DRF · Admin · Management Commands)

These functions are **safe to call from any synchronous context**:
DRF API views, Django admin actions, management commands, Celery tasks.

### `get_client_profile_or_none(user)`
Returns the `ClientProfile` for `user`, or `None` if not found.

```python
from apps.client.selectors.client_selectors import get_client_profile_or_none

profile = get_client_profile_or_none(request.user)
if profile is None:
    return Response({"detail": "Profile not found."}, status=404)
```

### `get_client_addresses(user)` / `list_client_addresses(user)`
Returns all non-deleted `ClientAddress` rows ordered by `-is_default, -created_at`.
`list_client_addresses` is an alias for backward compatibility.

### `get_client_stats(user)` → `dict`
Returns `{total_orders, total_spent_ngn, is_profile_complete, preferred_size}`.
Used by the JWT token serializer to embed quick stats in the login response.

### `get_client_address_list(user)` → `list[dict]`
Returns addresses as plain Python dicts for sync DRF/dashboard consumers.

### `get_client_order_stats(user)` → `dict`
Returns aggregated order statistics through `ClientProfile.get_order_stats_from_db()`.

### `get_client_dashboard_snapshot(user)` → `dict`
Returns the full sync client dashboard snapshot via model-level helpers.

---

## Async Selectors (Django-Ninja · ASGI · Uvicorn)

All async selectors use **Django 6.0 native async ORM terminals only**.
No `sync_to_async()` wrappers are used anywhere in this module.

### Native Async ORM Terminal Reference

| Terminal | Django Equivalent | Use Case |
|----------|-------------------|----------|
| `aget(...)` | `.get(...)` | Single object lookup |
| `afirst()` | `.first()` | First row or None |
| `acount()` | `.count()` | COUNT aggregate |
| `aexists()` | `.exists()` | EXISTS check |
| `aaggregate(...)` | `.aggregate(...)` | SUM/COUNT/AVG aggregates |
| `acreate(...)` | `.create(...)` | INSERT (services only) |
| `aupdate(...)` | `.update(...)` | UPDATE (services only) |
| `[row async for row in qs]` | list(qs) | Async QuerySet iteration |

---

### `aget_client_profile_or_none(user)` → `ClientProfile | None`
Async version of `get_client_profile_or_none`. Uses `aget()`.

```python
profile = await aget_client_profile_or_none(request.user)
```

### `alist_client_addresses(user)` → `list[ClientAddress]`
Returns model instances (not dicts). Use `aget_client_addresses()` for dict output.

### `acount_client_addresses(user)` → `int`
Returns count of non-deleted addresses. Single `acount()` call.

### `aget_client_addresses(user)` → `list[dict]`
Returns shipping addresses as plain dicts using `.values()` + async iteration.

```python
addresses = await aget_client_addresses(request.user)
# Returns: [{"id": ..., "label": ..., "city": ..., "is_default": True, ...}]
```

### `aget_client_address_list(user)` → `list[dict]`
Compatibility alias. Delegates to `ClientProfile.aget_address_list(user)`.

---

### `aget_client_order_summary(user)` → `dict` ⚡ Phase 8

> **Phase 8 Optimization:** This function previously ran 4 sequential `await` calls.
> It now uses `asyncio.gather()` to fire all 4 DB round-trips concurrently.
> Latency reduced from `~4 × DB_RTT ≈ 32ms` to `~1 × DB_RTT ≈ 8ms`.

Returns aggregated order statistics for the client dashboard hero card.

```python
summary = await aget_client_order_summary(request.user)
# Returns:
# {
#     "total_orders": 42,
#     "total_spent_ngn": 158750.00,
#     "pending_count": 3,
#     "active_count": 5,
#     "completed_count": 34,
# }
```

**Implementation (asyncio.gather):**
```python
(agg, pending_count, active_count, completed_count) = await asyncio.gather(
    qs.aaggregate(total_orders=Count("id"), total_spent_ngn=Sum("total_amount")),
    qs.filter(status=OrderStatus.PENDING_PAYMENT).acount(),
    qs.filter(status__in=[PAYMENT_CONFIRMED, PROCESSING, SHIPPED, OUT_FOR_DELIVERY]).acount(),
    qs.filter(status__in=[COMPLETED, DELIVERED]).acount(),
)
```

---

### `aget_client_order_stats(user)` → `dict`
Compatibility alias. Delegates to `ClientProfile.aget_order_stats_from_db(user)`.

### `aget_client_order_list(user, status=None, limit=20)` → `list[dict]`
Returns paginated order rows as dicts via `.values()` + async iteration.

```python
orders = await aget_client_order_list(request.user, limit=5)
# Returns: [{"order_number": ..., "status": ..., "total_amount": ..., ...}]
```

### `aget_client_wishlist(user, session_key=None)` → `list[dict]`
Returns wishlist items for an authenticated user or an anonymous session.

```python
# Authenticated:
wishlist = await aget_client_wishlist(request.user)

# Anonymous:
wishlist = await aget_client_wishlist(None, session_key=request.session.session_key)
```

### `aget_client_measurement_summary(user)` → `dict`
Returns the latest active measurement snapshot as a dict, or `{}` if none exists.
Uses `afirst()` on the measurement profile queryset with `.values()`.

### `aget_client_dashboard_snapshot(user)` → `dict`
Delegates to `ClientProfile.aget_full_dashboard_snapshot(user)`.

---

### `aget_client_dashboard_full(user)` → `dict` ⚡ Phase 8 — New

> **Phase 8:** Single function that loads the entire client dashboard in **one
> `asyncio.gather()` call** — 5 independent coroutines run concurrently.
> Use this in Ninja dashboard views instead of calling 5 selectors sequentially.

```python
from apps.client.selectors.client_selectors import aget_client_dashboard_full

dashboard = await aget_client_dashboard_full(request.user)
# Returns:
# {
#     "order_summary":  {"total_orders": 42, "total_spent_ngn": 158750.0, ...},
#     "address_count":  3,
#     "wishlist":       [...],
#     "measurement":    {"chest_cm": 95.0, ...},
#     "recent_orders":  [...],
# }
```

**Performance:** replaces 5 sequential `await` calls (`~5×8ms = 40ms`) with
a single `asyncio.gather()` (`~1×8ms = 8ms`) for the Ninja dashboard endpoint.

---

## Integration Guide

### Using Sync Selectors in DRF Views

```python
# apps/client/apis/sync/client_views.py
from apps.client.selectors.client_selectors import get_client_stats, get_client_addresses

class ClientDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stats = get_client_stats(request.user)
        addresses = list(get_client_addresses(request.user).values(...))
        return Response({"stats": stats, "addresses": addresses})
```

### Using Async Selectors in Django-Ninja Views

```python
# apps/client/apis/async_/client_views.py
from ninja import Router
from apps.client.selectors.client_selectors import aget_client_dashboard_full

router = Router()

@router.get("/dashboard/")
async def client_dashboard(request):
    # Phase 8: single gather call — all 5 coroutines run concurrently
    data = await aget_client_dashboard_full(request.user)
    return data
```

### Using in Celery Tasks

Selectors must NOT be called from async Celery task bodies.
Instead, use the **sync** variants and wrap the task as normal:

```python
# In a Celery task (sync context):
from apps.client.selectors.client_selectors import get_client_order_stats

@shared_task
def generate_client_report(user_id):
    user = UnifiedUser.objects.get(pk=user_id)
    stats = get_client_order_stats(user)
    # ... generate report
```

---

## Error Handling Policy

All selectors follow the **fail-safe** pattern:
- Sync selectors return `[]`, `{}`, `None`, or `0` on error — never raise.
- Async selectors return the same safe defaults on any exception.
- All exceptions are logged at `ERROR` level via the module logger.
- **Audit failures must never propagate to the user** — errors are swallowed
  silently and logged for monitoring.

---

## Testing Selectors

```python
# tests/client/test_selectors.py
import pytest
from django.test import TestCase

class TestAgetClientOrderSummary(TestCase):
    async def test_returns_zeros_for_new_user(self):
        from apps.client.selectors.client_selectors import aget_client_order_summary
        from tests.factories import UserFactory

        user = await UserFactory.acreate()
        result = await aget_client_order_summary(user)

        assert result["total_orders"] == 0
        assert result["pending_count"] == 0

    async def test_gather_concurrent_correctness(self):
        """All 4 DB queries run in parallel and return correct counts."""
        from apps.client.selectors.client_selectors import aget_client_order_summary
        # ... create test orders with known statuses
        # ... assert counts match
```

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v2.0 | 2026-05-30 | Phase 8: `asyncio.gather()` in `aget_client_order_summary`, new `aget_client_dashboard_full()` |
| v1.2 | 2026-05-15 | Added `aget_client_measurement_summary()`, anonymous wishlist support |
| v1.1 | 2026-04-10 | Phase 9 compliance fields; `ContextVar` migration (ASGI-safe) |
| v1.0 | 2026-03-01 | Initial selector layer — sync + async selectors, zero `sync_to_async` |
