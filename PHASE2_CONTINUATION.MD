# 🚀 PHASE2_CONTINUATION.MD — FASHIONISTAR BACKEND: WHERE WE STOPPED & WHERE WE GO NEXT

**Author:** Antigravity AI Agent (Senior Fullstack Architect, 10+ yrs enterprise/production)
**Date:** 2026-03-08
**Engine:** Django 6.0.2 + DRF + Django Ninja (Async)
**Scope:** Backend API development continuation — from Phase 1 completion → Phase 2 E-Commerce domain

---

## 📊 HONEST STATUS REPORT — WHERE WE ACTUALLY ARE RIGHT NOW

> [!IMPORTANT]
> This document is the authoritative "handoff ledger" between what has been built and what comes next. Every claim below was verified by reading source files directly — no assumptions.

### ✅ PHASE 0 — STABILIZATION (COMPLETE)

| Task | Status | Evidence |
|---|---|---|
| Django 6.0.2 (SQL injection patch) | ✅ DONE | Conversation: "Fixing Django SQL Injection" |
| `requirements.txt` audited | ✅ DONE | Verified during conversation 3 |
| `.env.example` present | ✅ DONE | `fashionistar_backend/.env.example` |
| Benchmark / stress tests created & run | ✅ DONE | `fashionistar_final_benchmark.py`, `fashionistar_stress_test.py` |
| Redis live (port 6379) | ✅ LIVE | Running terminal confirmed |
| Celery worker live | ✅ LIVE | Running terminal confirmed |

---

### ✅ PHASE 1 — BACKEND FOUNDATION & AUTH (SUBSTANTIALLY COMPLETE)

| Component | File / Location | Status |
|---|---|---|
| `UnifiedUser` model + `CustomUserManager` | `authentication/models.py` (19.8KB) + `managers.py` (7.7KB) | ✅ DONE |
| `UnifiedUserAdmin` (merged form, legacy-parity) | `authentication/admin.py` (27.5KB) | ✅ DONE |
| Auth serializers (Register, Login, OTP, Google, Password) | `authentication/serializers.py` (20.8KB) | ✅ DONE |
| **Split view files** (was monolith 36KB) | `apis/auth_views/sync_views.py` (17.8KB) + `async_views.py` (9.6KB) | ✅ DONE |
| Password views (split) | `apis/password_views/sync_views.py` + `async_views.py` | ✅ DONE |
| `RegistrationService` (sync + async) | `services/registration_service.py` | ✅ DONE |
| `OTPService` (sync + async, no `sync_to_async`) | `services/otp_service.py` | ✅ DONE |
| `SyncAuthService` / `AsyncAuthService` | `services/auth_service/sync_service.py` + `async_service.py` | ✅ DONE |
| `PasswordService` (sync + async) | `services/password_service/sync_service.py` + `async_service.py` | ✅ DONE |
| `SyncGoogleAuthService` | `services/google_service/` | ✅ DONE |
| Pydantic schemas | `types/auth_schemas.py` (3.6KB) | ✅ DONE |
| DRF Throttles | `throttles.py` | ✅ DONE |
| Auth backends (email+phone lookup) | `backends.py` | ✅ DONE |
| TaskLogger / audit trails | `tasks.py` (3.8KB) | ✅ DONE |
| **EventBus** | `apps/common/events.py` (9.4KB) | ✅ DONE |
| **RequestID middleware** | `apps/common/middleware.py` (13.6KB) | ✅ DONE |
| EmailManager / SMSManager (sync + async) | `apps/common/managers/` | ✅ DONE |
| CustomJSONRenderer | `apps/common/renderers.py` | ✅ DONE |
| CommonExceptions, Permissions, Throttling | `apps/common/exceptions.py`, `permissions.py`, `throttling.py` | ✅ DONE |
| Celery tasks (email, SMS) | `apps/common/tasks.py` (9.9KB) | ✅ DONE |
| Admin UI (UnifiedUser + signal/admin_mixin) | `apps/common/admin.py` (18.9KB) + `admin_mixins.py` (23KB) | ✅ DONE |

### ⚠️ PHASE 1 — REMAINING GAPS (Must close before Phase 2)

| Gap | File | Action Required |
|---|---|---|
| `LogoutView` body is a stub (no token blacklist) | `apis/auth_views/sync_views.py` L428-433 | Implement `RefreshToken` blacklist via SimpleJWT |
| Profile views exist as directory but not wired to URLs | `apis/profile_views/` | Wire to `authentication/urls.py` |
| `apps/authentication/urls.py` — confirm all routes wired | `authentication/urls.py` (2.5KB) | Audit: Login, Logout, Password Reset, Profile |
| `apps/common/selectors.py` — base selector missing | Not found in `apps/common/` | Create base selector patterns |
| `config/settings/` split — single `backend/settings.py` | `backend/settings.py` | Split → `base.py`, `development.py`, `production.py`, `logging.py` |
| Pytest infrastructure | No `tests/` root directory | Create `pytest.ini` + `tests/` with organized structure |
| `userauths/` legacy app still present | `fashionistar_backend/userauths/` | Deprecation + migration (Phase 1.6 from AGENT_PLAN) |

---

## 🗺️ PHASE 2 — WHAT WE DO NEXT (E-COMMERCE DOMAIN MIGRATION)

This section is the **official engineering continuation plan**, structured as actionable step-by-step tasks ordered by dependency.

---

### SPRINT 1 — CLOSE PHASE 1 GAPS (Priority: CRITICAL, ~1 day)

#### Task 1.1 — Implement Proper JWT Logout with Token Blacklist

**File:** `apps/authentication/apis/auth_views/sync_views.py`

**Why:** The `LogoutView` currently returns a stub response. Without server-side blacklisting, logged-out users can still use their refresh token to get new access tokens — a critical security vulnerability.

**Architecture (2025 Best Practice):**
```
Client sends POST /api/v1/auth/logout/
  → Body: { "refresh": "<refresh_token>" }
  → Server: attempts to blacklist the refresh token
  → SimpleJWT's OutstandingToken → BlacklistedToken
  → Response: 200 { "message": "Logout Successful" }
```

**Pre-requisite:** `rest_framework_simplejwt.token_blacklist` must be in `INSTALLED_APPS` and migrated.

**Implementation:**
```python
# apps/authentication/apis/auth_views/sync_views.py
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

class LogoutView(APIView):
    """
    User Logout — Blacklists the refresh token with SimpleJWT.

    Requires: IsAuthenticated (valid access token in Authorization header).
    Body: { "refresh": "<refresh_token>" }

    Success (200): { "message": "Logout Successful" }
    Error (400): Token already blacklisted or invalid.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request) -> Response:
        """Invalidates refresh token server-side."""
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            token = RefreshToken(refresh_token)
            token.blacklist()  # Requires token_blacklist in INSTALLED_APPS
            logger.info("✅ LogoutView: token blacklisted for user=%s", request.user.id)
            return Response(
                {"message": "Logout Successful. Your session has been terminated."},
                status=status.HTTP_200_OK
            )
        except TokenError as e:
            logger.warning("⚠️ LogoutView TokenError: %s", str(e))
            return Response(
                {"error": "Invalid or already expired token."},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error("❌ LogoutView error: %s", str(e), exc_info=True)
            return Response(
                {"error": "An error occurred during logout. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
```

**Settings to verify:**
```python
# backend/settings.py
INSTALLED_APPS = [
    ...
    'rest_framework_simplejwt.token_blacklist',  # ← Must be present
]

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),   # Short-lived
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),       # Long-lived
    'ROTATE_REFRESH_TOKENS': True,                    # New refresh on every use
    'BLACKLIST_AFTER_ROTATION': True,                 # Blacklist old refresh
    'AUTH_HEADER_TYPES': ('Bearer',),
}
```

**After implementing:** Run `python manage.py migrate` to create blacklist tables.

---

#### Task 1.2 — Audit & Complete Authentication URL Routing

**File:** `apps/authentication/urls.py`

**Action:** Ensure ALL endpoints are properly routed:

```python
# apps/authentication/urls.py — COMPLETE ROUTING MAP

from django.urls import path
from apps.authentication.apis.auth_views.sync_views import (
    RegisterView, LoginView, VerifyOTPView, ResendOTPView,
    GoogleAuthView, RefreshTokenView, LogoutView
)
from apps.authentication.apis.password_views.sync_views import (
    PasswordResetRequestView, PasswordResetConfirmView, PasswordChangeView
)

app_name = 'authentication'

urlpatterns = [
    # ── Registration Flow ──────────────────────────────────────────
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),

    # ── Login / Logout ─────────────────────────────────────────────
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', RefreshTokenView.as_view(), name='token-refresh'),

    # ── Password Management ─────────────────────────────────────────
    path('password/reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('password/change/', PasswordChangeView.as_view(), name='password-change'),

    # ── OAuth ──────────────────────────────────────────────────────
    path('google/', GoogleAuthView.as_view(), name='google-auth'),
]
```

**Test every route:** Use `python manage.py show_urls | grep api/v1/auth`.

---

#### Task 1.3 — Create `apps/common/selectors.py` (Base Selector Pattern)

**Why:** Selectors decouple queryset logic from views and services. Every Phase 2 domain module will inherit from this base.

```python
# apps/common/selectors.py
"""
Base Selector Pattern for Fashionistar.

Selectors encapsulate read-only QuerySet logic. They:
 - Live in `selectors.py` (or `selectors/` for large domains)
 - Accept typed parameters (never request objects)
 - Return QuerySets or typed dicts (never HTTP responses)
 - Use select_related/prefetch_related to prevent N+1 queries

Architecture Rule: Views call Services for writes; Views call Selectors for reads.
"""
from typing import Optional, Type, TypeVar
from django.db.models import Model, QuerySet

T = TypeVar('T', bound=Model)


class BaseSelector:
    """
    Base class providing common query helpers.

    Usage:
        class ProductSelector(BaseSelector):
            model = Product

            @classmethod
            def get_active(cls) -> QuerySet:
                return cls.model.objects.filter(is_active=True).select_related('vendor')
    """
    model: Type[T]

    @classmethod
    def get_by_id(cls, pk: str) -> Optional[T]:
        """Fetch single object by PK. Returns None if not found."""
        try:
            return cls.model.objects.get(pk=pk)
        except cls.model.DoesNotExist:
            return None

    @classmethod
    def get_by_id_or_raise(cls, pk: str) -> T:
        """Fetch single object by PK. Raises DoesNotExist if not found."""
        return cls.model.objects.get(pk=pk)

    @classmethod
    def get_all_active(cls) -> QuerySet:
        """Return all active records (requires `is_active` field)."""
        return cls.model.objects.filter(is_active=True)

    @classmethod
    def exists(cls, **kwargs) -> bool:
        """Check existence without fetching the full object."""
        return cls.model.objects.filter(**kwargs).exists()
```

---

#### Task 1.4 — Split Settings Module

**Why:** `backend/settings.py` as a single file is a Phase 0 gap. It mixes development and production concerns, making secrets management insecure and config management brittle.

**Target structure:**
```
config/
└── settings/
    ├── __init__.py        # Selects base/dev/prod via DJANGO_ENV env var
    ├── base.py            # Common settings (INSTALLED_APPS, MIDDLEWARE, etc.)
    ├── development.py     # DEBUG=True, SQLite, local email backend
    ├── production.py      # DEBUG=False, PostgreSQL, Redis, HTTPS settings
    └── logging.py         # Structured JSON logging configuration
```

**`config/settings/__init__.py`:**
```python
import os
env = os.environ.get('DJANGO_ENV', 'development')
if env == 'production':
    from .production import *
else:
    from .development import *
```

**`Makefile` + `Procfile` must be updated** to use `--settings=config.settings.development` or `--settings=config.settings.production`.

---

### SPRINT 2 — CREATE `apps/products/` DOMAIN (Priority: CRITICAL, ~3 days)

> [!IMPORTANT]
> This is the first of three major E-Commerce domain migrations.
> Source code to migrate FROM: `store/`, `Homepage/`
> Target: `apps/products/` with the full modular structure.

#### Task 2.1 — `apps/products/` Directory Scaffold

```
apps/products/
├── __init__.py
├── apps.py                     # ProductsConfig
├── models.py                   # Product, Category, Brand, ProductImage, Collection
├── admin.py                    # ProductAdmin with inline images
├── serializers.py              # ProductListSerializer, ProductDetailSerializer
├── selectors.py                # ProductSelector: get_active, get_by_vendor, search
├── services/
│   ├── __init__.py
│   ├── product_service.py      # CRUD logic: create_product, update_product, archive_product
│   └── search_service.py       # Full text search + future PgVector hooks
├── apis/
│   ├── __init__.py
│   ├── sync_views.py           # DRF: ProductListView, ProductDetailView, VendorProductView
│   └── async_views.py          # Ninja: async product search, trending products
├── types/
│   └── product_schemas.py      # Pydantic: ProductCreateSchema, ProductFilterSchema
├── tasks.py                    # Celery: reindex_products_task, image_resize_task
├── urls.py                     # URL patterns for /api/v1/products/
├── migrations/
│   └── __init__.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_services.py
    └── test_views.py
```

#### Task 2.2 — Product Models (Migrate from `store/` + `Homepage/`)

**Key models to port:**

```python
# apps/products/models.py
"""
Products Domain Models.
Migrated from: store/models.py, Homepage/models.py
Architecture: No cross-app FKs — uses UnifiedUser PK (UUID) as vendor_id field.
"""
import uuid
from django.db import models
from apps.common.models import TimeStampedModel  # Your timestamped base

class Category(TimeStampedModel):
    """Product category with slug for SEO-friendly URLs."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True, db_index=True)
    slug = models.SlugField(unique=True, max_length=250)
    image = models.ImageField(upload_to='categories/', null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ['name']
        indexes = [models.Index(fields=['slug', 'is_active'])]

class Brand(TimeStampedModel):
    """Brand/manufacturer entity."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

class Product(TimeStampedModel):
    """
    Core Product entity.
    Vendor reference uses vendor_id (UUID) — NO ForeignKey to apps/authentication.
    This maintains strict module boundary per architecture rules.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
        ('out_of_stock', 'Out of Stock'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor_id = models.UUIDField(db_index=True)           # Loose coupling to auth module
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True)

    name = models.CharField(max_length=300, db_index=True)
    slug = models.SlugField(unique=True, max_length=350)
    description = models.TextField()
    short_description = models.CharField(max_length=500, blank=True)

    price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    sku = models.CharField(max_length=100, unique=True, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor_id', 'status']),
            models.Index(fields=['category', 'status', 'is_featured']),
            models.Index(fields=['slug']),
        ]

    @property
    def effective_price(self):
        return self.discount_price if self.discount_price else self.price

    @property
    def is_in_stock(self):
        return self.stock_quantity > 0
```

#### Task 2.3 — Product Selectors

```python
# apps/products/selectors.py
from typing import Optional
from django.db.models import QuerySet
from apps.common.selectors import BaseSelector
from .models import Product, Category

class ProductSelector(BaseSelector):
    model = Product

    @classmethod
    def get_published(cls) -> QuerySet:
        """Published products for public API — optimized query."""
        return (
            cls.model.objects
            .filter(status='published')
            .select_related('category', 'brand')
            .prefetch_related('images')
            .only('id', 'name', 'slug', 'price', 'discount_price',
                  'stock_quantity', 'is_featured', 'category__name')
        )

    @classmethod
    def get_by_vendor(cls, vendor_id: str) -> QuerySet:
        """All products for a specific vendor (all statuses)."""
        return cls.model.objects.filter(vendor_id=vendor_id).order_by('-created_at')

    @classmethod
    def search(cls, query: str) -> QuerySet:
        """Basic text search — will be upgraded to PgVector in Phase 4."""
        from django.db.models import Q
        return cls.get_published().filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(brand__name__icontains=query)
        )

    @classmethod
    def get_featured(cls, limit: int = 10) -> QuerySet:
        return cls.get_published().filter(is_featured=True)[:limit]
```

#### Task 2.4 — DRF Sync Views for Products

```python
# apps/products/apis/sync_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from apps.products.selectors import ProductSelector
from apps.products.serializers import ProductListSerializer, ProductDetailSerializer
from apps.products.services.product_service import ProductService
from apps.common.renderers import CustomJSONRenderer
from apps.common.permissions import IsVendor  # Custom permission

class ProductListView(APIView):
    """Public product listing with pagination — GET /api/v1/products/"""
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    def get(self, request):
        try:
            products = ProductSelector.get_published()
            paginator = PageNumberPagination()
            paginator.page_size = 20
            page = paginator.paginate_queryset(products, request)
            serializer = ProductListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        except Exception as e:
            logger.error("❌ ProductListView error: %s", str(e), exc_info=True)
            return Response({"error": "Unable to retrieve products."}, status=500)

class ProductDetailView(APIView):
    """Single product detail — GET /api/v1/products/<slug>/"""
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    def get(self, request, slug: str):
        product = ProductSelector.get_by_id(pk=slug)  # or by slug
        if not product:
            return Response({"error": "Product not found."}, status=404)
        return Response(ProductDetailSerializer(product).data)

class VendorProductCreateView(APIView):
    """Vendor creates a product — POST /api/v1/products/create/"""
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request):
        try:
            result = ProductService.create_product(
                vendor_id=str(request.user.id),
                data=request.data
            )
            return Response(result, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error("❌ VendorProductCreateView: %s", str(e), exc_info=True)
            return Response({"error": "Failed to create product."}, status=500)
```

---

### SPRINT 3 — CREATE `apps/orders/` DOMAIN (Priority: HIGH, ~3 days)

> Source: `createOrder/`, `checkout/`, `ShopCart/`
> Target: `apps/orders/`

#### Task 3.1 — Orders Domain Scaffold

```
apps/orders/
├── models.py           # Cart, CartItem, Order, OrderItem, OrderStatus
├── selectors.py        # OrderSelector, CartSelector
├── services/
│   ├── cart_service.py       # add_to_cart, remove_from_cart, clear_cart
│   └── order_service.py      # create_order, cancel_order, update_status
├── apis/
│   ├── sync_views.py         # CartView, OrderListView, OrderDetailView
│   └── async_views.py        # Ninja: async order creation
├── tasks.py            # order_confirmation_email_task, order_status_notify_task
├── urls.py
└── tests/
```

#### Task 3.2 — Core Order Models

```python
# apps/orders/models.py
class Cart(TimeStampedModel):
    """Shopping cart — session or user-bound."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(null=True, blank=True, db_index=True)  # None = guest cart
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)

class CartItem(TimeStampedModel):
    """Individual cart line item."""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product_id = models.UUIDField()          # Loose coupling to products module
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)  # Snapshot at add-time

class Order(TimeStampedModel):
    """Confirmed order."""
    STATUS = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)
    order_number = models.CharField(max_length=20, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS, default='pending', db_index=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    shipping_address = models.JSONField()    # Address snapshot (no FK to address model)
    notes = models.TextField(blank=True)
    payment_reference = models.CharField(max_length=100, null=True, blank=True, db_index=True)
```

#### Task 3.3 — Order Service (Atomic Integrity)

```python
# apps/orders/services/order_service.py
from django.db import transaction
from apps.common.events import EventBus

class OrderService:

    @staticmethod
    @transaction.atomic
    def create_order(user_id: str, cart_id: str, shipping_address: dict) -> dict:
        """
        Creates order from cart. Atomic: either everything succeeds or nothing does.
        Pattern: transaction.on_commit() → Celery task (never inside atomic block).
        """
        from apps.orders.models import Cart, Order, OrderItem
        import uuid, random, string

        cart = Cart.objects.select_for_update().get(id=cart_id, user_id=user_id)
        items = cart.items.select_related().all()

        if not items.exists():
            raise ValueError("Cart is empty.")

        # Generate order number
        order_number = 'ORD-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

        # Calculate total
        total = sum(item.unit_price * item.quantity for item in items)

        order = Order.objects.create(
            user_id=user_id,
            order_number=order_number,
            status='pending',
            total_amount=total,
            shipping_address=shipping_address,
        )

        # Create order items
        OrderItem.objects.bulk_create([
            OrderItem(
                order=order,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
            )
            for item in items
        ])

        # Fire EventBus event AFTER successful transaction
        transaction.on_commit(
            lambda: EventBus.emit('order.created', {
                'order_id': str(order.id),
                'user_id': user_id,
                'total': float(total),
            })
        )

        # Clear cart post-commit
        transaction.on_commit(lambda: cart.items.all().delete())

        return {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'status': order.status,
            'total_amount': str(order.total_amount),
            'message': 'Order placed successfully. You will receive a confirmation shortly.',
        }
```

---

### SPRINT 4 — CREATE `apps/payments/` DOMAIN (Priority: HIGH, ~2 days)

> Source: `Paystack_Webhoook_Prod/`
> Target: `apps/payments/`

#### Task 4.1 — Payments Domain Scaffold

```
apps/payments/
├── models.py              # Payment, PaymentRefund, PaymentWebhookLog
├── selectors.py           # PaymentSelector
├── services/
│   ├── paystack_service.py # Paystack initialization, verify, refund
│   └── webhook_service.py  # Webhook validation, idempotent processing
├── apis/
│   ├── sync_views.py       # InitiatePaymentView, VerifyPaymentView
│   └── webhook_views.py    # PaystackWebhookView (dedicated file — high security)
├── tasks.py               # payment_confirmation_task, refund_notification_task
├── urls.py
└── tests/
    └── test_webhook.py     # Webhook signature validation tests
```

#### Task 4.2 — Idempotent Webhook Handler (Critical Pattern)

```python
# apps/payments/services/webhook_service.py
"""
Paystack Webhook Handler — Industrial Grade.

Key patterns:
1. Idempotency: Deduplicate via webhook_id lookup — never process twice.
2. Security: HMAC-SHA512 signature validation before ANY processing.
3. Atomic: DB write + business logic in one transaction.
4. on_commit: EventBus emission AFTER successful persistence.
"""
import hashlib, hmac
from django.db import transaction
from django.conf import settings
from apps.payments.models import Payment, PaymentWebhookLog
from apps.common.events import EventBus

class WebhookService:

    @staticmethod
    def validate_signature(payload: bytes, signature: str) -> bool:
        """HMAC-SHA512 signature validation. Called BEFORE any processing."""
        expected = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(),
            payload,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    @transaction.atomic
    def process_charge_success(event_data: dict) -> bool:
        """
        Process payment success webhook.
        Returns False if already processed (idempotent guard).
        """
        reference = event_data.get('data', {}).get('reference')

        # Idempotency check — read with lock
        if PaymentWebhookLog.objects.filter(reference=reference).exists():
            return False  # Already processed

        # Log webhook (prevents duplicate processing)
        PaymentWebhookLog.objects.create(
            reference=reference,
            event_type='charge.success',
            raw_payload=event_data,
        )

        # Update payment
        try:
            payment = Payment.objects.select_for_update().get(reference=reference)
            payment.status = 'success'
            payment.save(update_fields=['status', 'updated_at'])
        except Payment.DoesNotExist:
            return False

        # Notify downstream via EventBus (after commit)
        transaction.on_commit(
            lambda: EventBus.emit('payment.success', {
                'reference': reference,
                'order_id': str(payment.order_id),
                'amount': float(payment.amount),
            })
        )

        return True
```

---

### SPRINT 5 — `apps/authentication/` REMAINING WORK: PROFILE API

#### Task 5.1 — Wire Profile Views to URL Routing

The `apis/profile_views/` directory exists but was not wired in `urls.py`. This sprint ensures the Profile API is accessible:

**Endpoints to add:**
```
GET  /api/v1/auth/profile/          → Get own profile
PATCH /api/v1/auth/profile/         → Update own profile (name, bio, avatar)
POST /api/v1/auth/profile/avatar/   → Upload profile picture
```

---

## 🧪 TESTING STRATEGY FOR PHASE 2

### Infrastructure Setup

```bash
# Install pytest infrastructure
pip install pytest pytest-django pytest-asyncio pytest-cov factory-boy

# Create pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = backend.settings
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
```

### Test Coverage Targets

| Module | Minimum Coverage | Critical Test Cases |
|---|---|---|
| `authentication/` | 90% | Register → OTP → Login → Logout flow |
| `products/` | 85% | CRUD + permission checks for vendor vs client |
| `orders/` | 90% | Cart → Order → Status update + rollback scenarios |
| `payments/` | 95% | Webhook idempotency + signature validation |

### Verification Checklist for Each Module

Before marking any Phase 2 sprint as complete, verify:

```
☐ All model fields have DB indexes on filter/lookup columns
☐ All views use CustomJSONRenderer (consistent response format)
☐ All views have proper throttle_classes
☐ All write endpoints are wrapped in @transaction.atomic or equivalent service layer
☐ All Celery tasks called via transaction.on_commit(), never inside atomic block
☐ All EventBus emissions happen after transaction.on_commit()
☐ No cross-app ForeignKeys (loose coupling via UUID fields only)
☐ All serializer Meta classes use explicit `fields` list (not `__all__`)
☐ 100% type hints on all service methods
☐ pytest passes for all new tests
```

---

## 📡 API ENDPOINT REGISTRY (Updated State)

### Auth Module — `/api/v1/auth/` (DRF Sync)

| Method | Endpoint | View | Status |
|---|---|---|---|
| `POST` | `/register/` | `RegisterView` | ✅ Live |
| `POST` | `/verify-otp/` | `VerifyOTPView` | ✅ Live |
| `POST` | `/resend-otp/` | `ResendOTPView` | ✅ Live |
| `POST` | `/login/` | `LoginView` | ✅ Live |
| `POST` | `/logout/` | `LogoutView` | ⚠️ Stub — fix in Sprint 1 |
| `POST` | `/token/refresh/` | `RefreshTokenView` | ✅ Live |
| `POST` | `/google/` | `GoogleAuthView` | ✅ Live |
| `POST` | `/password/reset/` | `PasswordResetRequestView` | ✅ Live (verify wiring) |
| `POST` | `/password/reset/confirm/` | `PasswordResetConfirmView` | ✅ Live (verify wiring) |
| `POST` | `/password/change/` | `PasswordChangeView` | ✅ Live (verify wiring) |

### Auth Module — `/api/v2/auth/` (Django Ninja Async)

| Method | Endpoint | View | Status |
|---|---|---|---|
| `POST` | `/register` | Ninja `register()` | ✅ Live |
| `POST` | `/verify-otp` | Ninja `verify_otp()` | ✅ Live |
| `POST` | `/resend-otp` | Ninja `resend_otp()` | ✅ Live |
| `POST` | `/login` | Ninja `login()` | ✅ Live |

### Products Module — `/api/v1/products/` (To be built in Sprint 2)

| Method | Endpoint | View | Status |
|---|---|---|---|
| `GET` | `/` | `ProductListView` | 🔴 ToDo |
| `GET` | `/<slug>/` | `ProductDetailView` | 🔴 ToDo |
| `POST` | `/create/` | `VendorProductCreateView` | 🔴 ToDo |
| `PATCH` | `/<id>/` | `VendorProductUpdateView` | 🔴 ToDo |
| `DELETE` | `/<id>/` | `VendorProductArchiveView` | 🔴 ToDo |

### Orders Module — `/api/v1/orders/` (To be built in Sprint 3)

| Method | Endpoint | View | Status |
|---|---|---|---|
| `GET` | `/cart/` | `CartView` | 🔴 ToDo |
| `POST` | `/cart/add/` | `CartAddView` | 🔴 ToDo |
| `DELETE` | `/cart/remove/<id>/` | `CartRemoveView` | 🔴 ToDo |
| `POST` | `/create/` | `OrderCreateView` | 🔴 ToDo |
| `GET` | `/` | `OrderListView` | 🔴 ToDo |
| `GET` | `/<id>/` | `OrderDetailView` | 🔴 ToDo |

### Payments Module — `/api/v1/payments/` (To be built in Sprint 4)

| Method | Endpoint | View | Status |
|---|---|---|---|
| `POST` | `/initiate/` | `InitiatePaymentView` | 🔴 ToDo |
| `GET` | `/verify/<reference>/` | `VerifyPaymentView` | 🔴 ToDo |
| `POST` | `/webhook/paystack/` | `PaystackWebhookView` | 🔴 ToDo |

---

## ⚙️ ENGINEERING STANDARDS (Non-Negotiable Rules)

These rules apply to **every single file created in Phase 2**, without exception:

### 1. Module Boundary Rule
```python
# ❌ FORBIDDEN — Cross-app ForeignKey
class Order(Model):
    user = models.ForeignKey('authentication.UnifiedUser', ...)  # BREAKS MODULE BOUNDARY

# ✅ CORRECT — Loose coupling via UUID
class Order(Model):
    user_id = models.UUIDField(db_index=True)  # Store ID, look up via service if needed
```

### 2. Async/Sync Boundary Rule
```python
# ❌ FORBIDDEN
user = await sync_to_async(User.objects.get)(pk=pk)

# ✅ CORRECT
user = await User.objects.aget(pk=pk)
```

### 3. Transaction + EventBus Rule
```python
# ❌ FORBIDDEN — EventBus inside atomic block
with transaction.atomic():
    order.save()
    EventBus.emit('order.created', ...)  # WRONG — emits even if later code rolls back

# ✅ CORRECT
with transaction.atomic():
    order.save()
    transaction.on_commit(lambda: EventBus.emit('order.created', ...))  # After commit
```

### 4. Type Hints Rule
```python
# ❌ FORBIDDEN
def create_order(user_id, cart_id, address):
    pass

# ✅ CORRECT
from typing import Dict, Any
def create_order(user_id: str, cart_id: str, address: dict) -> Dict[str, Any]:
    pass
```

### 5. Serializer Rule
```python
# ❌ FORBIDDEN
class Meta:
    model = Product
    fields = '__all__'  # Exposes every field including sensitive ones

# ✅ CORRECT
class Meta:
    model = Product
    fields = ['id', 'name', 'slug', 'price', 'effective_price', 'category', 'brand']
```

---

## 📋 EXECUTION ORDER (Prioritized Task List)

Copy this checklist into task.md for the next session:

```
[ ] Sprint 1.1 — Implement full LogoutView with JWT token blacklist
[ ] Sprint 1.2 — Audit & complete authentication/urls.py routing
[ ] Sprint 1.3 — Create apps/common/selectors.py base selector
[ ] Sprint 1.4 — Split settings into config/settings/ module
[ ] Sprint 2.1 — Scaffold apps/products/ directory structure
[ ] Sprint 2.2 — Implement Product, Category, Brand, ProductImage models
[ ] Sprint 2.3 — Create ProductSelector with N+1-safe queries
[ ] Sprint 2.4 — Implement ProductService (create, update, archive)
[ ] Sprint 2.5 — Write DRF sync views (List, Detail, VendorCreate)
[ ] Sprint 2.6 — Write Ninja async views (Search, Trending)
[ ] Sprint 2.7 — Wire products/urls.py + register in main urls.py
[ ] Sprint 2.8 — Write product tests (models, services, views)
[ ] Sprint 3.1 — Scaffold apps/orders/ directory structure
[ ] Sprint 3.2 — Implement Cart, CartItem, Order, OrderItem models
[ ] Sprint 3.3 — Implement CartService (add, remove, clear)
[ ] Sprint 3.4 — Implement OrderService with atomic transaction + on_commit
[ ] Sprint 3.5 — DRF sync views for Cart + Order APIs
[ ] Sprint 3.6 — Wire orders/urls.py
[ ] Sprint 3.7 — Write order tests with rollback scenarios
[ ] Sprint 4.1 — Scaffold apps/payments/ directory structure
[ ] Sprint 4.2 — Implement Payment, WebhookLog models
[ ] Sprint 4.3 — PaystackService (initialize, verify, refund)
[ ] Sprint 4.4 — WebhookService with HMAC validation + idempotency
[ ] Sprint 4.5 — Wire payments/urls.py + webhook endpoint
[ ] Sprint 4.6 — Write webhook idempotency tests
[ ] Sprint 5.1 — Wire profile views to authentication/urls.py
[ ] Sprint 5.2 — Setup pytest.ini + organized tests/ root structure
[ ] Sprint 5.3 — Write integration test: Register → OTP → Login → Logout
[ ] Sprint 5.4 — Write integration test: Add to Cart → Create Order → Pay
```

---

## 🎯 PHASE 2 DEFINITION OF DONE (Exit Criteria)

Before moving to **Phase 3 (Frontend Architecture)**, ALL of the following must be verified:

| Gate | Verification Command / Check |
|---|---|
| Products API live | `curl http://localhost:8000/api/v1/products/` returns paginated JSON |
| Vendor can create product | `POST /api/v1/products/create/` with vendor JWT → 201 |
| Guest can browse products | `GET /api/v1/products/` without auth → 200 |
| Cart add/remove works | `POST /api/v1/orders/cart/add/` and `DELETE /api/v1/orders/cart/remove/{id}/` |
| Order creation is atomic | Create order → assert DB rollback on failure |
| Paystack webhook validated | Send fake webhook without signature → 403 |
| Webhook idempotent | Send same webhook twice → second is ignored |
| Logout blacklists token | Logout → use old refresh token → verify 401 |
| All tests pass | `pytest --cov=apps --cov-report=term-missing` → ≥ 85% coverage |
| No cross-app ForeignKeys | `grep -r "ForeignKey.*apps\." apps/` → 0 results |

---

**Document authored by:** Antigravity AI Agent (Senior Fullstack Architect)
**Next immediate action:** Begin **Sprint 1.1 — LogoutView JWT blacklist implementation**
**This document supersedes:** Relevant Phase 2 outline sections of `AGENT_PLAN.MD`
