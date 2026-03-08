# tests/conftest.py
"""
FASHIONISTAR — Global System Tests conftest
============================================
Located at:  tests/conftest.py  (one level below root conftest.py)

This file provides fixtures specific to SYSTEM-LEVEL tests:
  - tests/smoke/        → Site-wide health checks (DB, Redis, Celery, email)
  - tests/integration/  → Cross-app integration tests
  - tests/e2e/          → End-to-end full user journey tests

Inherits ALL fixtures from the root conftest.py automatically.

System test philosophy:
  - Smoke tests run on EVERY commit (CI fast-path)
  - Integration tests run on PR merge
  - E2E tests run on staging deploy
"""
import pytest


# ─────────────────────────────────────────────────────────────────────────────
#  DATABASE HEALTH
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
@pytest.mark.django_db
def db_health_check(db):
    """
    Verify the database is reachable and responsive.
    Used in: tests/smoke/test_smoke.py
    """
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
    return result[0] == 1


# ─────────────────────────────────────────────────────────────────────────────
#  REDIS HEALTH
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def redis_health_check():
    """
    Verify Redis is reachable and responsive.
    Returns True if Redis is healthy, False if unreachable.
    """
    try:
        from apps.common.utils import get_redis_connection_safe
        client = get_redis_connection_safe()
        if client:
            client.ping()
            return True
    except Exception:
        pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  FULL API CLIENT (Integration)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
@pytest.mark.django_db
def full_registration_flow(db, api_client):
    """
    Performs the FULL sync registration flow:
      1. POST /api/v1/auth/register/
      2. Manually activate the user (simulating OTP verification)
      3. POST /api/v1/auth/login/
      Returns dict: {user, access_token, refresh_token, response}
    """
    from apps.authentication.models import UnifiedUser

    # Step 1: Register
    payload = {
        'email': 'e2e@fashionistar.io',
        'password': 'IntegrationTest123!@#',
        'password2': 'IntegrationTest123!@#',
        'role': 'client',
    }
    reg_response = api_client.post('/api/v1/auth/register/', payload, format='json')

    # Step 2: Activate user (simulating OTP verification)
    user = UnifiedUser.objects.filter(email='e2e@fashionistar.io').first()
    if user:
        user.is_active = True
        user.is_verified = True
        user.save()

    # Step 3: Login
    login_payload = {
        'email_or_phone': 'e2e@fashionistar.io',
        'password': 'IntegrationTest123!@#',
    }
    login_response = api_client.post('/api/v1/auth/login/', login_payload, format='json')

    tokens = login_response.json().get('tokens', {})
    return {
        'user': user,
        'access_token': tokens.get('access'),
        'refresh_token': tokens.get('refresh'),
        'reg_response': reg_response,
        'login_response': login_response,
    }
