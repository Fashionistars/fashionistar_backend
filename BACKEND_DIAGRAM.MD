# FASHIONISTAR BACKEND ARCHITECTURE DIAGRAM

**Version:** 1.0 (Hybrid State)
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
│   │
│   └── authentication/         # [Identity Module - Refactored]
│       ├── apis/               # Dual-Engine API Layer
│       │   ├── auth_views/
│       │   │   ├── sync_views.py  # Standard DRF (Login/Reg)
│       │   │   └── async_views.py # Ninja/ADRF (High Perf)
│       │   ├── password_views/
│       │   ├── profile_views/
│       │   └── biometric_views/
│       ├── services/           # Business Logic Layer
│       ├── selectors/          # Read-Only Database Queries
│       ├── models.py           # CustomUser Models
│       ├── managers.py         # Custom Managers
│       ├── tasks.py            # Email/OTP Tasks
│       └── urls.py             # Module Routing
│
├── utilities/                  # Shared Utility Application
│   ├── django_redis.py         # Redis Caching Helpers
│   └── providers/              # Shared Service Providers
│
├── [LEGACY ROOT APPLICATIONS]  # Modules Pending Refactor
│   ├── store/                  # E-Commerce Catalog
│   │   ├── views.py            # Old Monolithic Views
│   │   ├── serializers.py
│   │   └── models.py
│   ├── userauths/              # Legacy Auth (Deprecated by apps/authentication)
│   ├── ShopCart/               # Cart Logic
│   ├── checkout/               # Payment Flows
│   ├── customer/               # Customer Profiles
│   ├── measurements/           # AI Measurement Implementation
│   ├── notification/           # Old Notification System
│   └── vendor/                 # Multi-Vendor Logic
│
├── manage.py                   # CLI Entry Point
├── requirements.txt            # Python Dependencies
├── Procfile                    # Deployment Process Type
├── render.yaml                 # Infrastructure as Code
└── build.sh                    # Build Scripts
```

## Legend

- **apps/**: Contains the new, refactored, production-grade code following the separation of concerns (Sync/Async).
- **backend/**: Pure configuration, no business logic.
- **Legacy Root Applications**: Older Django apps that are slowly being migrated into `apps/`.
