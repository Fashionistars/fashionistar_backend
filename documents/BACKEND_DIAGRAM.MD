# FASHIONISTAR BACKEND ARCHITECTURE DIAGRAM

**Version:** 1.1 (Comprehensive Mapping)
**Date:** January 2026
**Status:** In Progress (Migration from Root Apps to Modular `apps/` Structure)

## Directory Structure

```text
fashionistar_backend/
├── backend/                    # Project Configuration (Django 6.0)
│   ├── settings.py             # Main Settings
│   ├── asgi.py                 # Async Entry Point (Production)
│   ├── wsgi.py                 # Sync Entry Point
│   ├── urls.py                 # Main Routing Table
│   ├── celery.py               # Task Queue Entry
│   └── twilio.py               # SMS Config
│
├── apps/                       # MODERN DOMAIN LAYER (The Target Architecture)
│   ├── common/                 # Foundation Layer
│   │   ├── permissions.py      # RBAC & Policy
│   │   ├── exceptions.py       # Global Exception Handling
│   │   ├── utils.py            # Shared Helper Functions
│   │   ├── tasks.py            # Common Background Tasks
│   │   └── providers/          # External Integrations
│   │   ├── managers/
│   │
│   └── authentication/         # [Identity Module - Refactored]
│       ├── apis/
│       │   ├── auth_views/     # (sync_views.py, async_views.py)
│       │   ├── biometric_views/
│       │   ├── password_views/
│       │   └── profile_views/
│       ├── services/           # Business Logic
│       ├── selectors/          # Read-Only Logic
│       ├── models.py
│       ├── tasks.py
│       └── urls.py
│
├── utilities/                  # Shared Infrastructure
│   ├── django_redis.py
│   └── providers/
│
├── [LEGACY & ROOT APPLICATIONS]
│
│   ├── admin_backend/          # Custom Admin & Delivery Dashboard
│   │   ├── chat_view.py
│   │   ├── order_view.py
│   │   ├── delivery.py
│   │   └── signals.py
│   │
│   ├── Blog/                   # Content Management
│   │   ├── views.py
│   │   ├── models.py
│   │   └── serializers.py
│   │
│   ├── chat/                   # Real-time Chat (Channels)
│   │   ├── consumer.py         # WebSocket Consumers
│   │   ├── routing.py
│   │   └── views.py
│   │
│   ├── checkout/               # Payment Checkout Flow
│   │   ├── views.py
│   │   ├── utils.py
│   │   └── urls.py
│   │
│   ├── createOrder/            # Order Creation Logic
│   │   ├── order.py
│   │   └── urls.py
│   │
│   ├── customer/               # Customer Portal Logic
│   │   ├── profile.py
│   │   ├── orders.py
│   │   ├── wallet_balance.py
│   │   ├── wishlist.py
│   │   └── reviews.py
│   │
│   ├── Homepage/               # Landing Page & Product Features
│   │   ├── product.py
│   │   ├── brand.py
│   │   ├── category.py
│   │   └── collections.py
│   │
│   ├── measurements/           # AI Body Measurement
│   │   ├── views.py
│   │   ├── models.py
│   │   └── serializers.py
│   │
│   ├── notification/           # Notification System
│   │   ├── vendor_views.py
│   │   ├── client_views.py
│   │   └── utils.py
│   │
│   ├── Paystack_Webhoook_Prod/ # Payment Gateways
│   │   ├── webhook.py
│   │   ├── deposit.py
│   │   ├── BankAccountDetails.py
│   │   └── VendorWithdrawView.py
│   │
│   ├── ShopCart/               # Shopping Cart (Legacy)
│   │   ├── views.py
│   │   └── models.py
│   │
│   ├── store/                  # Main Catalog App
│   │   ├── views.py
│   │   ├── serializers.py
│   │   └── models.py
│   │
│   ├── userauths/              # Legacy Authentication (Deprecated)
│   │   ├── views.py
│   │   ├── models.py
│   │   └── admin.py
│   │
│   ├── vendor/                 # Multi-Vendor Dashboard
│   │   ├── dashboard.py
│   │   ├── model_chag_gpt.py
│   │   ├── views.py            # (100KB+ Monolithic View)
│   │   └── audit_log.py
│   │
│   ├── addon/                  # Extras/Plugins
│   │   └── views.py
│   │
│   └── api/                    # Legacy REST API Endpoints
│       └── views.py
│
├── manage.py
├── requirements.txt
├── Procfile
├── render.yaml
└── build.sh
```

## Architectural Status

*   **Green Zone (Modern/Safe)**: `apps/authentication`, `apps/common`, `backend/`
*   **Yellow Zone (Functional)**: `utilities/`, `chat/`, `Paystack_Webhoook_Prod/`
*   **Red Zone (Legacy/Refactor Needed)**: `admin_backend`, `userauths` (Duplicate of apps/auth), `vendor` (Monolithic views), `Homepage` (Mixed concerns).
