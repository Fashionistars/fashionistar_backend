# DJANGO 6.0 PRODUCTION IMPLEMENTATION BLUEPRINT

## Enterprise-Grade Backend Architecture for FASHIONISTAR AI eCommerce Platform

**Version:** 2.0 (Strict Async/Sync Separation)  
**Date:** January 25, 2026  
**Python Compatibility:** 3.12, 3.13, 3.14  
**Framework:** Django 6.0 (LTS Ready)  
**Architecture Pattern:** Modular Monolith with Microservice-Ready Separation

---

## TABLE OF CONTENTS

1. [Executive Overview](#executive-overview)
2. [Strict Async/Sync Architecture (The "No Mixed Mode" Rule)](#strict-asyncsync-architecture-the-no-mixed-mode-rule)
3. [Django 6.0 Native Async implementation](#django-60-native-async-implementation)
4. [Background Tasks (Django 6.0 Native Framework)](#background-tasks-django-60-native-framework)
5. [Enterprise Grade Recommendations (Top 5)](#enterprise-grade-recommendations-top-5)
6. [PostgreSQL Optimization & Connection Pooling](#postgresql-optimization--connection-pooling)
7. [Security & Content Security Policy (CSP)](#security--content-security-policy-csp)
8. [Event-Driven Architecture (Signal Replacement)](#event-driven-architecture-signal-replacement)
9. [Detailed Implementation Roadmap](#detailed-implementation-roadmap)

---

## EXECUTIVE OVERVIEW

This document mandates a **STRICT** architectural separation for the FASHIONISTAR backend. To achieve "Industrial Enterprise Grade" performance and reliability, we are enforcing the following core directives:

> [!IMPORTANT]
> **CORE DIRECTIVES**
>
> 1. **NO ADRF**: We do NOT use `adrf` or any hybrid async wrappers for DRF.
> 2. **SYNC = DRF**: All synchronous, standard CRUD operations MUST use **Django REST Framework (DRF)**.
> 3. **ASYNC = NINJA**: All asynchronous, high-performance, I/O-bound endpoints MUST use **Django Ninja**.
> 4. **NATIVE ASYNC ONLY**: We strictly use Django 6.0's native async methods (`aget`, `acreate`, `afilter`, `aall`).
> 5. **CONCURRENCY**: We MUST use `asyncio.gather()` for all multiple API/ORM queries in async views.

---

## STRICT ASYNC/SYNC ARCHITECTURE (The "No Mixed Mode" Rule)

We strictly separate our API layer into two distinct frameworks based on the nature of the operation.

### 1. SYNCHRONOUS DOMAIN (Django REST Framework)

**Use Case**: Complex business logic, heavy serialization, admin operations, standard relational CRUD.

- **ORM Usage**: Native blocking calls (`objects.get()`, `objects.filter()`).
- **Serialization**: DRF `ModelSerializer`.
- **Views**: `generics.ListCreateAPIView`, `viewsets.ModelViewSet`.

```python
# apps/orders/apis/sync/views.py
from rest_framework import generics
from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer

class OrderListCreateView(generics.ListCreateAPIView):
    """
    Standard Sync API for Order Management.
    Uses DRF for robust validation and complex relational handling.
    """
    queryset = Order.objects.select_related('customer').all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # Sync business logic here
        serializer.save(user=self.request.user)
```

### 2. ASYNCHRONOUS DOMAIN (Django Ninja)

**Use Case**: High-concurrency I/O, AI Processing, Real-time Data, Aggregation, Webhooks.

- **ORM Usage**: **Strictly** Native Async (`aget()`, `acreate()`, `afilter()`, `aall()`).
- **Serialization**: Pydantic Schemas (`Schema`).
- **Views**: Async functions (`async def`).

```python
# apps/orders/apis/async/api.py
from ninja import NinjaAPI, Schema
from apps.orders.models import Order
from typing import List
import asyncio

api = NinjaAPI()

class OrderSchema(Schema):
    id: int
    status: str
    total: float

@api.get("/orders/async-stats", response=List[OrderSchema])
async def get_order_stats(request):
    """
    Async Endpoint using Django Ninja.
    Demonstrates 'afilter', 'aall', and 'asyncio.gather'.
    """
    # Native Async ORM
    active_orders = await Order.objects.filter(status='active').aall()

    # Example of concurrency with asyncio.gather
    # Fetching multiple independent data sources in parallel
    task1 = Order.objects.filter(status='pending').acount()
    task2 = Order.objects.filter(status='shipped').acount()

    pending_count, shipped_count = await asyncio.gather(task1, task2)

    return active_orders
```

---

## DJANGO 6.0 NATIVE ASYNC IMPLEMENTATION

We leverage the full suite of native async ORM methods provided by Django 6.0. **Do not use `sync_to_async` wrappers for DB calls that have native support.**

### Supported Native Methods Checklist:

- [x] `Model.objects.aget(pk=1)`
- [x] `Model.objects.acreate(name="Item")`
- [x] `Model.objects.aget_or_create(defaults={...})`
- [x] `Model.objects.aupdate_or_create(defaults={...})`
- [x] `QuerySet.acount()`
- [x] `QuerySet.aexists()`
- [x] `QuerySet.aall()` (Async Iteration: `async for obj in ...`)
- [x] `QuerySet.afilter()` (Chaining is allowed, evaluation must be async)
- [x] `Model.asave()`
- [x] `Model.adelete()`

### Concurrency Pattern (Mandatory)

When performing multiple independent I/O operations (DB queries or external API calls), **you must use `asyncio.gather()`**.

```python
import asyncio
from asgiref.sync import sync_to_async

async def dashboard_data(request):
    """
    Fetch all dashboard metrics in PARALLEL.
    """
    # 1. Define coroutines (do not await them yet)
    task_user = request.user.aget_partner()
    task_orders = Order.objects.filter(user=request.user).acount()
    task_revenue = calculate_revenue_async(request.user) # Hypothetical async service

    # 2. Execute concurrently
    partner, order_count, revenue = await asyncio.gather(
        task_user,
        task_orders,
        task_revenue
    )

    return {"partner": partner, "orders": order_count, "revenue": revenue}
```

---

## BACKGROUND TASKS (DJANGO 6.0 NATIVE FRAMEWORK)

We are adopting the new Django Tasks framework, backed by **Redis Cluster**.

### Architecture

- **Broker**: Redis Cluster (High Availability).
- **Worker**: Standard Django 6.0 worker process.
- **Queues**: Segmented by priority (`critical`, `default`, `low_priority`).

### Implementation Strategy

```python
# apps/common/tasks.py
from django.tasks import task
from django.core.mail import send_mail
import logging

logger = logging.getLogger("django.tasks")

@task(priority=10, queue_name="critical")
def send_critical_alert(user_id: int, message: str):
    """
    Critical system alert.
    """
    try:
        # Native async not fully supported inside sync tasks, so we use standard sync calls
        # The task ITSELF runs in the background.
        send_mail(
            "System Alert",
            message,
            "admin@fashionistar.com",
            [f"user_{user_id}@example.com"],
            fail_silently=False
        )
    except Exception as e:
        logger.error(f"Task Failed: {e}", exc_info=True)
        raise e
```

---

## ENTERPRISE GRADE RECOMMENDATIONS (TOP 5)

We are implementing strict "Industrial Enterprise Grade" infrastructure recommendations.

### 1. **Connection Pooling with PgBouncer** (MANDATORY)

- **Why**: Async Django opens many connections. Without pooling, we risk DB exhaustion (`FATAL: remaining connection slots are reserved...`).
- **Config**: Run `PgBouncer` purely in **Transaction Mode**.
- **Target**: Support 10,000+ concurrent users with minimal DB overhead.

### 2. **Structured Logging (ELK Stack Compatible)**

- **Requirement**: JSON formatted logs.
- **Must Include**: `request_id`, `user_id`, `path`, `execution_time`.
- **Purpose**: Trace async calls across the system (Logstash -> Elasticsearch -> Kibana).

```python
# settings/production.py
LOGGING = {
    'version': 1,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO'},
    }
}
```

### 3. **Redis Cluster (Tasks & Cache)**

- **Why**: Single-node Redis is a Single Point of Failure (SPOF).
- **Implementation**: Configure `django-redis` to use cluster mode for caching and the Tasks backend.
- **Scale**: Enables horizontal scaling of the background job queue.

### 4. **OpenTelemetry (Distributed Tracing)**

- **Critical For**: Debugging Async/Sync boundaries.
- **Goal**: Pinpoint 10ms slowdowns. Identify if a delay is in the Async View, the DB Query, or the External API.
- **Tooling**: Auto-instrument Django and Requests/Httpx.

### 5. **Kubernetes HPA (Horizontal Pod Autoscaling)**

- **Strategy**: Scale independently based on:
  - **CPU**: For API Pods (Django Ninja/DRF).
  - **Queue Depth**: For Worker Pods (Django Tasks).
- **Manifest**:
  ```yaml
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  ```

---

## POSTGRESQL OPTIMIZATION & CONNECTION POOLING

### Advanced Configuration

- **Engine**: `django.db.backends.postgresql`
- **Async Interface**: `psycopg` (v3) is required for Django 6.0 async support.
- **Full-Text Search**: Native `SearchVector`, `SearchQuery`.
- **Vector Search**: `pgvector` for AI implementations (Embeddings).

```python
# settings/production.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'fashionistar_db',
        'USER': 'fashionistar',
        'OPTIONS': {
            'connect_timeout': 10,
            # If using PgBouncer, disable client-side keepalives or tune them
        },
        'CONN_MAX_AGE': 600, # Persistent connections (tuned for PgBouncer)
    }
}
```

---

## SECURITY & CONTENT SECURITY POLICY (CSP)

Django 6.0 includes built-in CSP management (`django.middleware.security.CSPMiddleware`).

### Strict Policy

- **Default**: `self` only.
- **Scripts**: Disallow inline scripts (unless nonced).
- **Connect**: Restrict to our API and trusted 3rd parties (Stripe/Paystack).

```python
SECURE_CSP = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "https://cdn.jsdelivr.net"],
    "connect-src": ["'self'", "https://api.stripe.com"],
    "img-src": ["'self'", "data:", "https://res.cloudinary.com"],
}
```

---

## EVENT-DRIVEN ARCHITECTURE (Signal Replacement)

**Directive**: DO NOT USE DJANGO SIGNALS (`post_save`, `pre_save`). They are synchronous, implicit, and hard to debug.

**Solution**: Explicit Async Event Bus.

```python
# apps/common/events.py
import asyncio
from typing import Callable, List

class AsyncEventBus:
    subscribers: dict[str, List[Callable]] = {}

    @classmethod
    def subscribe(cls, event: str, handler: Callable):
        if event not in cls.subscribers:
            cls.subscribers[event] = []
        cls.subscribers[event].append(handler)

    @classmethod
    async def emit(cls, event: str, *args, **kwargs):
        if event in cls.subscribers:
            # Execute all handlers concurrently
            tasks = [handler(*args, **kwargs) for handler in cls.subscribers[event]]
            await asyncio.gather(*tasks)

# Usage
# await AsyncEventBus.emit("order_created", order_id=123)
```

---

## DETAILED IMPLEMENTATION ROADMAP

1.  **Refactor Phase**:
    - [ ] Create `apps/routers/ninja_urls.py` for new Async APIs.
    - [ ] Create `apps/routers/drf_urls.py` for existing Sync APIs.
    - [ ] Audit all views: If it's pure CRUD -> Enable DRF. If it's simple/high-load -> Move to Ninja.
2.  **Infrastructure Phase**:
    - [ ] Deploy `PgBouncer` sidecar container.
    - [ ] Set up Redis Cluster (Minimum 3 nodes).
    - [ ] Configure ELK stack log shippers.
3.  **Code Migration**:
    - [ ] Rewrite all existing `adrf` views to **Django Ninja**.
    - [ ] Convert manual `sync_to_async(objects.get)` calls to `objects.aget()`.
    - [ ] Implement `asyncio.gather` for dashboard/stats endpoints.
4.  **Security Phase**:
    - [ ] Enable `CSPMiddleware`.
    - [ ] Audit `requirements.txt` for Python 3.12+ compatibility.
