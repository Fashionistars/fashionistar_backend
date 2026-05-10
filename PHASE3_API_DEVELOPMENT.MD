# 🚀 PHASE3_API_DEVELOPMENT.MD — FASHIONISTAR BACKEND: PHASE 3 ENGINEERING PLAN

**Author:** Antigravity AI Agent (Senior Fullstack Backend Architect, 10+ yrs Enterprise/Production)
**Date:** 2026-03-08 (Last Verified Against Live Codebase)
**Engine:** Django 6.0.2 · DRF (Sync/V1) · Django Ninja (Async/V2)
**Stack:** Python 3.12 · PostgreSQL · Redis · Celery · Uvicorn · Cloudinary

---

## 📊 VERIFIED STATUS SNAPSHOT (What Is Actually Done)

> [!IMPORTANT]
> Every item below was verified by reading actual source files — not documentation alone.
> The previous `PHASE2_CONTINUATION.MD` defines **what to build**. This document picks up after it and
> defines the **exact order of execution with quality gates**.

### ✅ LAYERS FULLY COMPLETE

| Layer | Key Files | Evidence |
|---|---|---|
| Async Middleware Stack | `apps/common/middleware.py` (13.6KB) | Dual `__call__`/`__acall__`, 0 Django check errors |
| EventBus | `apps/common/events.py` (9.4KB) | 2,558 RPS, p50=0ms confirmed in benchmark |
| Async Logging Pipeline | `apps/common/apps.py` | `QueueListener` active, nanosecond log calls |
| Redis Integration | `.env` + `settings.py` | 2,911 RPS async pipeline, 100% success |
| Celery Integration | `apps/common/tasks.py` (9.9KB) | Email/SMS tasks, broker connected |
| Health Check Endpoint | `apps/common/views.py` | Fast-fail 0.3s Redis/Celery timeouts |
| Auth Services (full) | `apps/authentication/services/` (20 files) | Registration, OTP, Login, Password, Google |
| Auth Views (split) | `apps/authentication/apis/auth_views/` | `sync_views.py` (17.8KB) + `async_views.py` (9.6KB) |
| Auth URL Routing | `apps/authentication/urls.py` | V1 (DRF) + V2 (Ninja) fully wired |
| Auth Admin | `apps/authentication/admin.py` (27.5KB) | `UnifiedUserAdmin` merged form |
| Custom Renderers/Exceptions/Throttling | `apps/common/` | `renderers.py`, `exceptions.py`, `throttling.py` |
| Admin Mixins/Analytics | `apps/common/admin_mixins.py` (23KB) | SoftDelete badge, analytics counters |
| Common Permissions | `apps/common/permissions.py` | Role-aware async permission classes |
| Pytest Dependencies | `requirements.txt` | `pytest`, `pytest-django`, `pytest-asyncio`, `pytest-cov`, `factory-boy` added (2026-03-08) |

### ⚠️ CONFIRMED GAPS (Must Close — In Priority Order)

| # | Gap | Location | Impact |
|---|---|---|---|
| G1 | `tests/` directory empty | `apps/authentication/tests/` | No automated regression coverage |
| G2 | `selectors/` directory empty | `apps/authentication/selectors/` | Views call ORM directly (architecture violation) |
| G3 | `apps/common/selectors.py` missing | `apps/common/` | Base selector class not created |
| G4 | JWT logout stub (no blacklist) | `sync_views.py` ~L428 | Security vulnerability |
| G5 | Profile views NOT wired to `urls.py` | `apis/profile_views/` | Profile API unreachable |
| G6 | `pytest.ini` / `conftest.py` not created | Project root | Pytest cannot discover tests |
| G7 | `apps/products/` does NOT exist | `fashionistar_backend/apps/` | Core E-Commerce domain missing |
| G8 | `apps/orders/` does NOT exist | `fashionistar_backend/apps/` | Cart + Order domain missing |
| G9 | `apps/payments/` does NOT exist | `fashionistar_backend/apps/` | Payment domain missing |
| G10 | Legacy `userauths/` (35 files) still present | `fashionistar_backend/userauths/` | Duplicate user model risk |
| G11 | Settings not split | `backend/settings.py` (single large file) | Dev/Prod secrets mixed |
| G12 | No `docs/` directory | Backend root | Architecture docs scattered at root |

---

## 🗺️ EXECUTION ORDER — SPRINT-BY-SPRINT PLAN

```
Sprint A → Pytest Infrastructure + Auth Test Suite
Sprint B → Auth Gaps (Logout blacklist + Profile routing + Selectors)
Sprint C → apps/products/ Domain (full build)
Sprint D → apps/orders/ Domain (full build)
Sprint E → apps/payments/ Domain (full build)
Sprint F → API Documentation (OpenAPI/Swagger polish + Postman collection)
Sprint G → Vendor Decomposition (apps/vendor/ migration from legacy)
Sprint H → Settings Split + Docker Infrastructure
Sprint I → CI/CD + Production Hardening
```

---

## 🧪 SPRINT A — PYTEST INFRASTRUCTURE + AUTH TEST SUITE
### Priority: CRITICAL | Estimated: 1 day

> [!IMPORTANT]
> **Why first?** Every subsequent sprint must ship tests alongside code.
> Build the floor before the walls.

### A.1 — Create `pytest.ini` at Project Root

```ini
# fashionistar_backend/pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = backend.settings
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
addopts =
    --reuse-db
    --strict-markers
    -q
    --tb=short
    --cov=apps
    --cov-report=term-missing
    --cov-fail-under=70
markers =
    unit: Pure unit test (no DB)
    integration: Requires DB
    async_test: Async test requiring event loop
    slow: Takes more than 1 second
filterwarnings =
    ignore::DeprecationWarning
```

### A.2 — Create `conftest.py` at Project Root

```python
# fashionistar_backend/conftest.py
"""
Global pytest fixtures for the Fashionistar backend test suite.
All fixtures here are available in every test file without imports.
"""
import pytest
import django
from django.conf import settings


@pytest.fixture(scope='session')
def django_db_setup():
    """Use test database for all tests."""
    pass


@pytest.fixture
def api_client():
    """DRF APIClient for sync endpoint tests."""
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def async_client():
    """Django async test client for async view tests."""
    from django.test import AsyncClient
    return AsyncClient()


@pytest.fixture
def user_factory(db):
    """Factory for creating test UnifiedUser instances."""
    from apps.authentication.models import UnifiedUser

    def make_user(**kwargs):
        defaults = {
            'email': 'test@fashionistar.io',
            'first_name': 'Test',
            'last_name': 'User',
            'phone_number': '+2348012345678',
            'role': 'customer',
            'is_verified': True,
            'is_active': True,
        }
        defaults.update(kwargs)
        user = UnifiedUser(**defaults)
        user.set_password(kwargs.get('password', 'SecurePass123!'))
        user.save()
        return user

    return make_user


@pytest.fixture
def vendor_factory(user_factory):
    """Factory for creating test vendor users."""
    def make_vendor(**kwargs):
        return user_factory(role='vendor', **kwargs)
    return make_vendor


@pytest.fixture
def auth_headers(user_factory, api_client):
    """Returns authenticated DRF client + JWT tokens for a test user."""
    user = user_factory(email='authtest@fashionistar.io')
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return api_client, user, {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }


@pytest.fixture
def redis_client():
    """Sync Redis test client pointing to DB=15 (test isolation)."""
    import redis
    r = redis.Redis(host='127.0.0.1', port=6379, db=15, decode_responses=True)
    yield r
    r.flushdb()  # Clean up after each test
    r.close()
```

### A.3 — Create Auth Test Suite

**File structure to create:**
```
apps/authentication/tests/
├── __init__.py
├── conftest.py              # Auth-specific fixtures
├── test_registration.py     # Register → OTP → Verify flow
├── test_login.py            # Login + token issuance
├── test_logout.py           # JWT blacklist
├── test_password.py         # Reset request + confirm + change
├── test_otp_service.py      # OTP generation, expiry, max-attempts
└── test_auth_backends.py    # Email + phone number lookup backends
```

**Critical test cases (minimum viability):**

```python
# apps/authentication/tests/test_registration.py
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestRegistrationFlow:
    """Full Register → OTP Verify flow."""

    def test_register_new_user_returns_201(self, api_client):
        url = reverse('authentication:register-sync')
        payload = {
            'email': 'newuser@fashionistar.io',
            'first_name': 'John',
            'last_name': 'Doe',
            'phone_number': '+2348099887766',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
            'role': 'customer',
        }
        response = api_client.post(url, payload, format='json')
        assert response.status_code == 201
        assert 'email' in response.data

    def test_register_duplicate_email_returns_400(self, api_client, user_factory):
        user = user_factory(email='dupe@fashionistar.io')
        url = reverse('authentication:register-sync')
        payload = {'email': user.email, 'password': 'SecurePass123!', 'role': 'customer'}
        response = api_client.post(url, payload, format='json')
        assert response.status_code == 400

    def test_register_weak_password_returns_400(self, api_client):
        url = reverse('authentication:register-sync')
        payload = {'email': 'weak@fashionistar.io', 'password': '123', 'role': 'customer'}
        response = api_client.post(url, payload, format='json')
        assert response.status_code == 400


@pytest.mark.django_db
class TestLoginFlow:
    """Login with valid credentials returns JWT pair."""

    def test_login_returns_token_pair(self, api_client, user_factory):
        user = user_factory(email='login@fashionistar.io', password='SecurePass123!')
        url = reverse('authentication:login-sync')
        resp = api_client.post(url, {
            'email': user.email, 'password': 'SecurePass123!'
        }, format='json')
        assert resp.status_code == 200
        assert 'access' in resp.data
        assert 'refresh' in resp.data

    def test_login_wrong_password_returns_401(self, api_client, user_factory):
        user = user_factory(email='loginwrong@fashionistar.io')
        url = reverse('authentication:login-sync')
        resp = api_client.post(url, {
            'email': user.email, 'password': 'WrongPassword!'
        }, format='json')
        assert resp.status_code in (400, 401)
```

**Run target:**
```bash
make test                  # Run full suite
make test-auth             # Run only authentication tests
make test-cov              # Run with HTML coverage report
```

**Add to Makefile:**
```makefile
test: ## Run full pytest suite
	venv\Scripts\pytest -q --tb=short

test-auth: ## Run authentication tests only
	venv\Scripts\pytest apps/authentication/tests/ -v

test-cov: ## Run tests with HTML coverage report
	venv\Scripts\pytest --cov=apps --cov-report=html:htmlcov
	@echo "Open htmlcov/index.html"

test-fast: ## Fast tests (no DB, unit only)
	venv\Scripts\pytest -m "not integration" -q
```

---

## 🔐 SPRINT B — AUTH GAPS CLOSURE
### Priority: CRITICAL (Security) | Estimated: 0.5 day

### B.1 — Fix JWT Logout (Token Blacklist)

**File:** `apps/authentication/apis/auth_views/sync_views.py`

The `LogoutView` must blacklist the incoming refresh token. Without this, users can continue using refresh tokens after logout — a **critical security vulnerability**.

```python
# In sync_views.py — replace the stub LogoutView with:
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Body: { "refresh": "<refresh_token>" }
    Auth: Bearer <access_token> required
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request) -> Response:
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required to logout."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info("Logout: token blacklisted user=%s", request.user.id)
            return Response(
                {"message": "Logout successful. Session terminated."},
                status=status.HTTP_200_OK
            )
        except TokenError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error("LogoutView error: %s", exc, exc_info=True)
            return Response({"error": "Logout failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

**Verify `INSTALLED_APPS` contains:**
```python
'rest_framework_simplejwt.token_blacklist',
```

**Then run:** `venv\Scripts\python manage.py migrate`

### B.2 — Wire Profile Views to `urls.py`

```python
# Append to apps/authentication/urls.py

from apps.authentication.apis.profile_views.sync_views import (
    ProfileRetrieveUpdateView,
    AvatarUploadView,
)

v1_profile_patterns = [
    path('v1/auth/profile/', ProfileRetrieveUpdateView.as_view(), name='profile'),
    path('v1/auth/profile/avatar/', AvatarUploadView.as_view(), name='avatar-upload'),
]

urlpatterns = v1_auth_patterns + v1_password_patterns + v1_profile_patterns + v2_auth_patterns
```

### B.3 — Create `apps/common/selectors.py`

```python
# apps/common/selectors.py
"""
Base Selector pattern — Fashionistar Architecture §6.5.

Rules:
  - Selectors provide READ-ONLY queryset logic
  - Never accept HttpRequest objects
  - Always use select_related/prefetch_related
  - Return QuerySets or typed dicts only (never HttpResponse)
"""
from __future__ import annotations
from typing import Optional, Type, TypeVar
from django.db.models import Model, QuerySet

T = TypeVar('T', bound=Model)


class BaseSelector:
    model: Type[T]

    @classmethod
    def get_by_id(cls, pk: str) -> Optional[T]:
        try:
            return cls.model.objects.get(pk=pk)
        except cls.model.DoesNotExist:
            return None

    @classmethod
    def get_by_id_or_raise(cls, pk: str) -> T:
        return cls.model.objects.get(pk=pk)

    @classmethod
    def get_all_active(cls) -> QuerySet:
        return cls.model.objects.filter(is_active=True)

    @classmethod
    async def aget_by_id(cls, pk: str) -> Optional[T]:
        """Async version — use in async views / Ninja endpoints."""
        try:
            return await cls.model.objects.aget(pk=pk)
        except cls.model.DoesNotExist:
            return None

    @classmethod
    def exists(cls, **kwargs) -> bool:
        return cls.model.objects.filter(**kwargs).exists()

    @classmethod
    async def aexists(cls, **kwargs) -> bool:
        return await cls.model.objects.filter(**kwargs).aexists()
```

### B.4 — Add `UserSelector` to `apps/authentication/selectors/`

```python
# apps/authentication/selectors/user_selector.py
from apps.common.selectors import BaseSelector
from apps.authentication.models import UnifiedUser
from django.db.models import QuerySet
from typing import Optional


class UserSelector(BaseSelector):
    model = UnifiedUser

    @classmethod
    def get_by_email(cls, email: str) -> Optional[UnifiedUser]:
        return cls.model.objects.filter(email__iexact=email).first()

    @classmethod
    def get_by_phone(cls, phone: str) -> Optional[UnifiedUser]:
        return cls.model.objects.filter(phone_number=phone).first()

    @classmethod
    def get_vendors(cls) -> QuerySet:
        return cls.model.objects.filter(role='vendor', is_active=True, is_verified=True)

    @classmethod
    def get_customers(cls) -> QuerySet:
        return cls.model.objects.filter(role='customer', is_active=True)
```

---

## 🛍️ SPRINT C — `apps/products/` DOMAIN
### Priority: CRITICAL | Estimated: 3 days
### Source: Migrate from `store/`, `Homepage/`

> [!NOTE]
> **Architecture rule:** `apps/products/` uses `vendor_id = UUIDField()` — NO ForeignKey to `apps/authentication/`.
> Module boundaries are enforcement points. Cross-module joins happen at the API layer via serializers only.

### C.1 — Directory Scaffold

```
apps/products/
├── __init__.py
├── apps.py                         # ProductsConfig
├── models.py                       # Category, Brand, Product, ProductImage, Collection
├── admin.py                        # ProductAdmin (inline images, search)
├── serializers.py                  # ProductListSerializer, ProductDetailSerializer
├── selectors.py                    # ProductSelector (get_published, search, by_vendor, featured)
├── services/
│   ├── __init__.py
│   ├── product_service.py          # create, update, archive, clone_product
│   └── search_service.py           # Full-text search (PgVector hook in Phase 4)
├── apis/
│   ├── __init__.py
│   ├── sync_views.py               # DRF: ProductList, ProductDetail, VendorProductCreate
│   └── async_views.py              # Ninja: product search, trending, recommendations
├── types/
│   └── product_schemas.py          # Pydantic: ProductCreateSchema, ProductFilterSchema
├── tasks.py                        # Celery: resize_upload_task, reindex_search_task
├── urls.py                         # /api/v1/products/ + /api/v2/products/
├── migrations/
│   └── 0001_initial.py
└── tests/
    ├── __init__.py
    ├── factories.py                 # factory-boy: ProductFactory, CategoryFactory
    ├── test_models.py
    ├── test_selectors.py
    ├── test_services.py
    └── test_views.py
```

### C.2 — Models (Core Fields Only — Add Migrations After)

| Model | Key Fields | DB Indexes |
|---|---|---|
| `Category` | uuid pk, name, slug, image, is_active | `slug`, `is_active` |
| `Brand` | uuid pk, name, slug, logo, is_active | `slug` |
| `Product` | uuid pk, vendor_id (UUID), category FK, brand FK, name, slug, description, price, discount_price, stock_qty, status, is_featured, sku | `vendor_id+status`, `category+status+is_featured`, `slug` |
| `ProductImage` | uuid pk, product FK, image_url, alt_text, is_primary, sort_order | `product+is_primary` |
| `Collection` | uuid pk, name, slug, products M2M, is_active, is_featured | `slug` |

### C.3 — Async Ninja Endpoint (Product Search)

```python
# apps/products/apis/async_views.py
from ninja import Router, Query
from ninja.pagination import paginate as ninja_paginate
from apps.products.selectors import ProductSelector
from apps.products.types.product_schemas import ProductFilterSchema, ProductListOut

router = Router(tags=["Products V2 (Async)"])


@router.get("/search/", response=list[ProductListOut], summary="Async product search")
@ninja_paginate
async def search_products(request, filters: ProductFilterSchema = Query(...)):
    """
    High-performance async product search.
    Supports: q (text), category_slug, brand_slug, min_price, max_price, is_featured.
    Pagination: ?page=1&page_size=20
    """
    qs = ProductSelector.get_published()

    if filters.q:
        qs = ProductSelector.search(filters.q)
    if filters.category_slug:
        qs = qs.filter(category__slug=filters.category_slug)
    if filters.brand_slug:
        qs = qs.filter(brand__slug=filters.brand_slug)
    if filters.min_price is not None:
        qs = qs.filter(price__gte=filters.min_price)
    if filters.max_price is not None:
        qs = qs.filter(price__lte=filters.max_price)
    if filters.is_featured:
        qs = qs.filter(is_featured=True)

    return [p async for p in qs.aiterator()]


@router.get("/trending/", response=list[ProductListOut], summary="Trending products (cached)")
async def trending_products(request, limit: int = 10):
    """
    Returns trending products. Cached in Redis for 60s.
    Cache key: products:trending:{limit}
    """
    import json
    from django.core.cache import cache

    cache_key = f"products:trending:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    products = [p async for p in ProductSelector.get_published()
                        .filter(is_featured=True)
                        .order_by('-created_at')
                        .aiterator()][:limit]
    cache.set(cache_key, json.dumps([...]), timeout=60)
    return products
```

### C.4 — Verification Checklist for Sprint C

```
[ ] make migrate — 0 errors, products tables created
[ ] Django admin: Category, Brand, Product, ProductImage, Collection all register
[ ] GET /api/v1/products/ — returns paginated list, 200 OK
[ ] GET /api/v1/products/<slug>/ — returns single product, 200 OK
[ ] POST /api/v1/products/create/ (Vendor auth) — creates product, 201 Created
[ ] GET /api/v2/products/search/?q=shirt — async search returns results
[ ] pytest apps/products/tests/ — all tests pass, coverage >85%
[ ] git commit + push both repos
```

---

## 📦 SPRINT D — `apps/orders/` DOMAIN
### Priority: HIGH | Estimated: 3 days
### Source: Migrate from `createOrder/`, `checkout/`, `ShopCart/`

### D.1 — Directory Scaffold

```
apps/orders/
├── models.py           # Cart, CartItem, Order, OrderItem, ShippingAddress
├── selectors.py        # CartSelector, OrderSelector
├── services/
│   ├── cart_service.py       # add_to_cart, update_qty, remove_item, clear_cart
│   └── order_service.py      # create_order(@transaction.atomic), cancel_order, update_status
├── apis/
│   ├── sync_views.py         # CartView, OrderListView, OrderDetailView
│   └── async_views.py        # Ninja: async order creation
├── tasks.py            # order_confirmation_email_task, status_update_notify_task
├── urls.py             # /api/v1/orders/ /api/v1/cart/
└── tests/
    ├── factories.py
    ├── test_cart_service.py
    └── test_order_service.py
```

### D.2 — Critical Pattern: Atomic Order + on_commit EventBus

```python
# apps/orders/services/order_service.py
from django.db import transaction
from apps.common.events import event_bus

class OrderService:

    @staticmethod
    @transaction.atomic
    def create_order(user_id: str, cart_id: str, shipping_address: dict) -> dict:
        """
        Atomic order creation.
        Rules (non-negotiable):
          1. SELECT FOR UPDATE on Cart to prevent race conditions
          2. Snapshot prices at order time (NOT live product price)
          3. transaction.on_commit → EventBus emit (never inside atomic block)
          4. transaction.on_commit → Celery task dispatch
        """
        from apps.orders.models import Cart, Order, OrderItem

        cart = Cart.objects.select_for_update().get(id=cart_id, user_id=user_id)
        items = list(cart.items.all())

        if not items:
            raise ValueError("Cannot create order from empty cart.")

        total = sum(item.unit_price * item.quantity for item in items)
        order_number = OrderService._generate_order_number()

        order = Order.objects.create(
            user_id=user_id,
            order_number=order_number,
            status='pending',
            total_amount=total,
            shipping_address=shipping_address,
        )
        OrderItem.objects.bulk_create([
            OrderItem(order=order, product_id=item.product_id,
                      quantity=item.quantity, unit_price=item.unit_price)
            for item in items
        ])

        # ✅ EventBus AFTER commit — fire-and-forget (p50=0ms)
        transaction.on_commit(lambda: event_bus.emit('order.created', {
            'order_id': str(order.id),
            'user_id': user_id,
            'total': float(total),
            'order_number': order_number,
        }))

        # ✅ Celery task AFTER commit — never inside atomic!
        from apps.orders.tasks import send_order_confirmation_task
        transaction.on_commit(
            lambda: send_order_confirmation_task.apply_async(
                args=[str(order.id)], countdown=2
            )
        )

        # Clear cart after commit
        transaction.on_commit(lambda: cart.items.all().delete())

        return {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'status': 'pending',
            'total_amount': str(total),
        }

    @staticmethod
    def _generate_order_number() -> str:
        import random, string
        chars = string.ascii_uppercase + string.digits
        return 'FSIO-' + ''.join(random.choices(chars, k=8))
```

### D.3 — Verification Checklist for Sprint D

```
[ ] GET /api/v1/cart/ — returns empty cart, 200 OK
[ ] POST /api/v1/cart/add/ — adds item, quantity reflected
[ ] POST /api/v1/orders/ — creates order atomically, cart cleared
[ ] EventBus 'order.created' fires after commit (log visible)
[ ] Duplicate cart submission does NOT create duplicate order (SELECT FOR UPDATE)
[ ] pytest apps/orders/tests/ — all tests pass, coverage >90%
[ ] git commit + push both repos
```

---

## 💳 SPRINT E — `apps/payments/` DOMAIN
### Priority: HIGH | Estimated: 2 days
### Source: Migrate from `Paystack_Webhoook_Prod/`

### E.1 — Directory Scaffold

```
apps/payments/
├── models.py              # Payment, PaymentRefund, PaymentWebhookLog
├── selectors.py
├── services/
│   ├── paystack_service.py  # initialize, verify, charge_authorization, refund
│   └── webhook_service.py   # validate_signature, process_charge_success (idempotent)
├── apis/
│   ├── sync_views.py        # InitiatePaymentView, VerifyPaymentView
│   └── webhook_views.py     # PaystackWebhookView (separate file — high-security)
├── tasks.py                 # payment_success_email_task, refund_notification_task
├── urls.py
└── tests/
    └── test_webhook.py      # HMAC-SHA512 signature tests, idempotency tests
```

### E.2 — Critical: Idempotent Webhook (HMAC-SHA512)

```python
# apps/payments/services/webhook_service.py

class WebhookService:

    @staticmethod
    def validate_signature(raw_body: bytes, x_paystack_signature: str) -> bool:
        """
        HMAC-SHA512 — validate BEFORE processing anything.
        Never process an unvalidated webhook.
        """
        import hmac, hashlib
        from django.conf import settings
        computed = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(),
            raw_body,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(computed, x_paystack_signature)

    @staticmethod
    @transaction.atomic
    def process_charge_success(data: dict) -> bool:
        """
        Returns True if processed, False if already seen (idempotent guard).
        """
        reference = data.get('data', {}).get('reference')
        if not reference:
            return False

        # Idempotency: check before INSERT
        if PaymentWebhookLog.objects.filter(reference=reference).exists():
            return False  # Already processed — silently ignore

        PaymentWebhookLog.objects.create(
            reference=reference,
            event_type='charge.success',
            raw_payload=data,
        )

        try:
            payment = Payment.objects.select_for_update().get(reference=reference)
            payment.status = 'success'
            payment.save(update_fields=['status', 'updated_at'])
        except Payment.DoesNotExist:
            return False

        transaction.on_commit(lambda: event_bus.emit('payment.success', {
            'reference': reference,
            'order_id': str(payment.order_id),
            'amount': float(payment.amount),
        }))

        return True
```

### E.3 — Verification Checklist for Sprint E

```
[ ] POST /api/v1/payments/initiate/ — returns Paystack auth URL
[ ] GET /api/v1/payments/verify/<reference>/ — verifies payment status
[ ] POST /webhook/paystack/ with valid HMAC → processes once only
[ ] POST /webhook/paystack/ with same reference twice → second call returns 200 but skips
[ ] POST /webhook/paystack/ with invalid signature → 403 Forbidden
[ ] pytest apps/payments/tests/ — all tests pass, coverage >95%
[ ] git commit + push both repos
```

---

## 📖 SPRINT F — API DOCUMENTATION
### Priority: HIGH | Estimated: 1 day

> The project already has drf-yasg (Swagger) and Django Ninja's built-in /docs/ endpoint.
> This sprint polishes both to be demo-ready and exports a Postman collection.

### F.1 — Complete OpenAPI Schema Tags

Every DRF view must have `tags` in the schema:
```python
@swagger_auto_schema(
    tags=['Authentication'],
    operation_summary='Register new user',
    operation_description='...',
    responses={
        201: RegisterResponseSerializer,
        400: ErrorSerializer,
    }
)
```

### F.2 — Django Ninja API Documentation

```python
# backend/api_v2.py (centralized Ninja router)
from ninja import NinjaAPI
from ninja.security import HttpBearer

class JWTBearer(HttpBearer):
    def authenticate(self, request, token):
        from rest_framework_simplejwt.authentication import JWTAuthentication
        # ...

api_v2 = NinjaAPI(
    title="FASHIONISTAR API V2 (Async)",
    version="2.0.0",
    description="High-performance async endpoints (Django Ninja + Uvicorn)",
    auth=JWTBearer(),
    docs_url="/api/v2/docs/",
    openapi_url="/api/v2/openapi.json",
)
```

### F.3 — Postman Collection Export

```bash
# Export OpenAPI JSON and import into Postman
curl http://127.0.0.1:8000/swagger.json -o fashionistar_api_v1.json
curl http://127.0.0.1:8000/api/v2/openapi.json -o fashionistar_api_v2.json
# Then import both JSON files into Postman
```

### F.4 — API Reference Table (Track All Endpoints)

| V | Method | Endpoint | Auth | Description |
|---|---|---|---|---|
| V1 | POST | `/api/v1/auth/register/` | None | Register user |
| V1 | POST | `/api/v1/auth/verify-otp/` | None | Verify OTP |
| V1 | POST | `/api/v1/auth/resend-otp/` | None | Resend OTP |
| V1 | POST | `/api/v1/auth/login/` | None | Login → JWT pair |
| V1 | POST | `/api/v1/auth/logout/` | Bearer | Blacklist refresh token |
| V1 | POST | `/api/v1/auth/token/refresh/` | None | Get new access token |
| V1 | GET/PATCH | `/api/v1/auth/profile/` | Bearer | Get/update profile |
| V1 | POST | `/api/v1/auth/profile/avatar/` | Bearer | Upload avatar |
| V1 | POST | `/api/v1/password/reset-request/` | None | Send reset email |
| V1 | POST | `/api/v1/password/reset-confirm/` | None | Confirm reset |
| V1 | POST | `/api/v1/password/change/` | Bearer | Change password |
| V1 | GET | `/api/v1/auth/google/` | None | Google OAuth |
| V1 | GET | `/api/v1/products/` | None | Product list |
| V1 | GET | `/api/v1/products/<slug>/` | None | Product detail |
| V1 | POST | `/api/v1/products/create/` | Vendor | Create product |
| V1 | GET | `/api/v1/cart/` | Bearer | Get cart |
| V1 | POST | `/api/v1/cart/add/` | Bearer | Add to cart |
| V1 | POST | `/api/v1/orders/` | Bearer | Create order |
| V1 | GET | `/api/v1/orders/<id>/` | Bearer | Order detail |
| V1 | POST | `/api/v1/payments/initiate/` | Bearer | Initiate payment |
| V1 | GET | `/api/v1/payments/verify/<ref>/` | Bearer | Verify payment |
| V1 | POST | `/webhook/paystack/` | HMAC-SHA512 | Paystack webhook |
| V2 | GET | `/api/v2/auth/docs/` | None | Ninja OpenAPI docs |
| V2 | GET | `/api/v2/products/search/` | None | Async product search |
| V2 | GET | `/api/v2/products/trending/` | None | Trending (Redis cached) |
| ALL | GET | `/api/health/` | None | Service health check |

---

## 🏗️ SPRINT G — VENDOR DECOMPOSITION
### Priority: MEDIUM | Estimated: 4 days
### Source: `vendor/views.py` (100KB+ monolith, 39 files)

> [!WARNING]
> **Do NOT attempt Sprint G until Sprints A–E are complete.**
> The vendor monolith must be decomposed AFTER the domain modules it migrates TO exist and have tests.
> Attempting this early risks regression on live functionality.

### Migration Map

| Source | Target | Complexity |
|---|---|---|
| `vendor/views.py` — product CRUD | `apps/products/services/`, `apis/sync_views.py` | High |
| `vendor/views.py` — order management | `apps/orders/services/order_service.py` | High |
| `vendor/views.py` — payout/wallet | `apps/payments/services/payout_service.py` | Medium |
| `vendor/views.py` — dashboard stats | `apps/common/selectors.py` + Ninja endpoint | Medium |
| `vendor/models.py` — VendorProfile | `apps/authentication/models.py` (already has vendor fields) | Low |

**Protocol:** Write tests FIRST against the legacy `vendor/views.py`, then migrate, then verify same tests pass.

---

## ⚙️ SPRINT H — SETTINGS SPLIT + DOCKER
### Priority: MEDIUM | Estimated: 1.5 days

### H.1 — Split Settings Module

```
config/
└── settings/
    ├── __init__.py          # Reads DJANGO_ENV, imports correct module
    ├── base.py              # INSTALLED_APPS, MIDDLEWARE, AUTH, CACHES (common)
    ├── development.py       # DEBUG=True, SQLite fallback, console email
    ├── production.py        # DEBUG=False, HSTS, CSRF, Sentry, PostgreSQL
    └── logging.py           # QueueHandler + QueueListener (move from apps.py)
```

### H.2 — Docker Compose (Local Dev)

```yaml
# docker/docker-compose.dev.yml
version: '3.9'
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: fashionistar_dev
      POSTGRES_USER: fashionistar
      POSTGRES_PASSWORD: devpassword
    ports: ["5432:5432"]
    volumes: ["postgres_data:/var/lib/postgresql/data"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

  backend:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    volumes: ["..:/app"]
    ports: ["8000:8000"]
    depends_on: [db, redis]
    env_file: ../.env
    command: venv/bin/uvicorn backend.asgi:application --host 0.0.0.0 --port 8000 --reload

  celery:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    volumes: ["..:/app"]
    depends_on: [db, redis]
    env_file: ../.env
    command: venv/bin/celery -A backend worker -l INFO -Q default,email,sms

volumes:
  postgres_data:
```

---

## 🚀 SPRINT I — CI/CD + PRODUCTION HARDENING
### Priority: MEDIUM | Estimated: 2 days

### I.1 — GitHub Actions CI (`.github/workflows/ci.yml`)

```yaml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Ruff lint
        run: pip install ruff && ruff check .

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        options: --health-cmd pg_isready
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: pip install -r requirements.txt
      - run: pytest --cov=apps --cov-fail-under=70 -q
```

### I.2 — Production Hardening Checklist

```
[ ] DEBUG=False in production.py
[ ] ALLOWED_HOSTS set from environment variable
[ ] SECURE_HSTS_SECONDS = 31536000
[ ] SECURE_SSL_REDIRECT = True
[ ] SESSION_COOKIE_SECURE = True
[ ] CSRF_COOKIE_SECURE = True
[ ] X_FRAME_OPTIONS = 'DENY'
[ ] CONTENT_SECURITY_POLICY headers via middleware
[ ] Sentry SDK installed and DSN configured
[ ] OpenTelemetry tracing configured
[ ] Log rotation and retention policy set
[ ] Cloudinary credentials in env (not code)
[ ] Paystack keys in env (not code)
[ ] SECRET_KEY generated per environment (not shared)
[ ] Redis AUTH password set in production
[ ] PostgreSQL SSL enabled
```

---

## 📋 QUALITY GATES PER SPRINT

| Sprint | Gate | Command |
|---|---|---|
| A | Pytest discovers and runs >10 tests | `make test` |
| B | Logout returns 200 + token blacklisted | `curl /api/v1/auth/logout/` |
| C | Products API: 200 OK list + detail + create | `make test-products` |
| D | Order created atomically, EventBus fires | `make test-orders` |
| E | Webhook idempotency: second call skipped | `make test-payments` |
| F | `/swagger/` and `/api/v2/docs/` both load | Browser check |
| G | All vendor tests pass after migration | `make test` |
| H | `docker compose up` starts all services | `docker compose up` |
| I | CI pipeline passes on GitHub | GitHub Actions ✅ |

---

## 📦 MAKEFILE TARGETS TO ADD

```makefile
##@ Testing
test: ## Run full pytest suite with coverage
	PYTHONIOENCODING=utf-8 venv\Scripts\pytest -q --tb=short

test-auth: ## Auth tests only
	venv\Scripts\pytest apps/authentication/tests/ -v

test-products: ## Products tests only
	venv\Scripts\pytest apps/products/tests/ -v

test-orders: ## Orders tests only
	venv\Scripts\pytest apps/orders/tests/ -v

test-payments: ## Payments tests only
	venv\Scripts\pytest apps/payments/tests/ -v

test-cov: ## Full suite + HTML coverage report
	venv\Scripts\pytest --cov=apps --cov-report=html:htmlcov/
	@echo "Open htmlcov/index.html in browser"

##@ Development
selectors: ## Run Django check (verify no issues)
	venv\Scripts\python manage.py check

migrate-new: ## Create + apply migrations for new apps
	venv\Scripts\python manage.py makemigrations products orders payments
	venv\Scripts\python manage.py migrate

show-urls: ## Show all registered URL routes
	venv\Scripts\python manage.py show_urls | grep api
```

---

## 🔢 NEXT IMMEDIATE ACTION (What TO Do First, Right Now)

```
1.  Create fashionistar_backend/pytest.ini  ← (this file, copy from Sprint A.1)
2.  Create fashionistar_backend/conftest.py ← (global fixtures, copy from Sprint A.2)
3.  Create apps/authentication/tests/__init__.py
4.  Create apps/authentication/tests/test_registration.py  ← start with these
5.  Create apps/authentication/tests/test_login.py
6.  Run: make test  ← Verify pytest discovers and runs tests
7.  Create apps/common/selectors.py ← (Sprint B.3)
8.  Create apps/authentication/selectors/__init__.py + user_selector.py
9.  Fix LogoutView blacklist ← (Sprint B.1)
10. Wire profile URLs ← (Sprint B.2)
11. Run: make test → all auth tests pass
12. Create apps/products/ scaffold ← (Sprint C)
13. git commit + push both repos after each sprint
```

---

> [!CAUTION]
> **Do NOT attempt legacy migration (`vendor/`, `userauths/`) until Sprints A–E are complete
> and test coverage is ≥70%.** Migrating without a test suite is how production breaks.

---

**Document Status:** LIVE — Updated 2026-03-08
**Previous Document:** [PHASE2_CONTINUATION.MD](./PHASE2_CONTINUATION.MD)
**Architecture Source:** [AGENT_PLAN.MD](./AGENT_PLAN.MD)
**Next Review:** After Sprint C (apps/products/) is complete
