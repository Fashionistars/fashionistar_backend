"""
apps/catalog/tests/conftest.py
==============================
Catalog-level pytest fixtures shared across:
  - test_catalog_api.py
  - test_homepage_bundle.py    (G1/G2)
  - test_catalog_concurrency.py (G5)

All fixtures use SQLite :memory: (backend/config/test.py) — no Postgres/Redis needed.
Redis-dependent fixtures are skipped automatically by conftest.py _probe_redis logic.

Usage:
    pytest apps/catalog/tests/ -v
"""
from __future__ import annotations

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Core catalog seed — provides all model instances used in G1/G2/G5
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def catalog_seed(db):
    """
    Seed minimal catalog data for homepage bundle selector tests.

    Creates:
      - 1 Category: "Test Category" (active)
      - 1 Brand: "Test Brand" (active)
      - 1 Collection: "Test Collection" (active, is_featured=True)
      - 1 CatalogBanner: "Hero Banner" (hero slot, is_active=True, no expiry)

    Returns a dict with all created instances for fine-grained assertions.
    """
    from apps.catalog.models import Category, Collections
    from apps.catalog.models.banner import CatalogBanner

    # Import Brand — handle both possible model locations
    try:
        from apps.catalog.models import Brand
    except ImportError:
        from apps.catalog.models.brand import Brand  # type: ignore[no-redef]

    cat = Category.objects.create(
        name="Test Category",
        slug="test-category",
        active=True,
    )
    brand = Brand.objects.create(
        title="Test Brand",
        slug="test-brand",
        active=True,
    )
    coll = Collections.objects.create(
        title="Test Collection",
        slug="test-collection",
        sub_title="Test subtitle",
        description="A test collection.",
        is_featured=True,
    )
    banner = CatalogBanner.objects.create(
        slot="hero",
        title="Hero Banner",
        subtitle="The best deals",
        cta_text="Shop Now",
        cta_url="/products",
        is_active=True,
        sort_order=1,
    )

    return {
        "category": cat,
        "brand": brand,
        "collection": coll,
        "banner": banner,
    }


@pytest.fixture
def seeded_db(db):
    """
    Lighter seed for concurrency tests — only creates category and collection.
    Avoids creating unnecessary objects that slow down 50x concurrent tests.
    """
    from apps.catalog.models import Category, Collections

    Category.objects.create(
        name="Concurrency Test Cat",
        slug="concurrency-test-cat",
        active=True,
    )
    Collections.objects.create(
        title="Concurrency Test Coll",
        slug="concurrency-test-coll",
        sub_title="Sub",
        description="Test",
    )


# ─────────────────────────────────────────────────────────────────────────────
# API clients
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sync_client():
    """Unauthenticated DRF APIClient — for integration endpoint tests."""
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def async_client(db):
    """Django AsyncClient — for Django-Ninja async endpoint tests."""
    from django.test import AsyncClient
    return AsyncClient()


@pytest.fixture
def staff_client(db):
    """
    Authenticated APIClient logged in as a staff user.
    Used for testing admin-only endpoints like /catalog/admin/invalidate-cache/
    """
    from rest_framework.test import APIClient
    from apps.authentication.models import UnifiedUser

    staff = UnifiedUser.objects.create_user(
        email="staff@fashionistar.io",
        password="StaffPass123!",
        role="client",
        is_active=True,
        is_verified=True,
        is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(user=staff)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# Cache utilities
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_catalog_cache():
    """
    Auto-use: clear Django DummyCache before each test.

    Since backend/config/test.py uses DummyCache, this is effectively a no-op,
    but it ensures test isolation if someone runs with a real cache backend.
    """
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Pytest markers for catalog test suite
# ─────────────────────────────────────────────────────────────────────────────


def pytest_configure(config):
    """Register catalog-specific markers (supplement pytest.ini markers)."""
    config.addinivalue_line(
        "markers", "concurrency: Concurrency and race-condition tests"
    )
    config.addinivalue_line(
        "markers", "catalog: Catalog app tests"
    )
    config.addinivalue_line(
        "markers", "bundle: Homepage bundle tests (G1/G2)"
    )
