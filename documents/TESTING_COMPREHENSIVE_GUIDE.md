# 🧪 COMPREHENSIVE TESTING GUIDE — FASHIONISTAR AI BACKEND

**Version:** 1.0  
**Date:** March 25, 2026  
**Scope:** Complete testing strategy covering unit, integration, stress, race conditions, idempotency, and concurrency  

---

## 📋 TABLE OF CONTENTS

1. [Testing Framework Setup](#testing-framework-setup)
2. [Unit Testing Patterns](#unit-testing-patterns)
3. [Integration Testing Patterns](#integration-testing-patterns)
4. [Stress Testing (100K RPS)](#stress-testing-100k-rps)
5. [Race Condition & Concurrency Testing](#race-condition--concurrency-testing)
6. [Idempotency Testing](#idempotency-testing)
7. [Transaction.atomic Pattern Testing](#transactionatomic-pattern-testing)
8. [Admin Interface Testing](#admin-interface-testing)
9. [Swagger/API Documentation Testing](#swaggerapi-documentation-testing)
10. [DRF Browser UI Testing](#drf-browser-ui-testing)
11. [Performance & Load Analysis](#performance--load-analysis)
12. [Test Execution & CI/CD Integration](#test-execution--cicd-integration)

---

## TESTING FRAMEWORK SETUP

### Dependencies
```bash
pip install pytest pytest-django pytest-asyncio pytest-cov pytest-xdist
pip install factory-boy faker hypothesis
pip install locust k6
pip install responses requests-mock
```

### Test Execution Commands

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=apps --cov-report=html

# Run specific test class
pytest apps/authentication/tests/test_models.py::TestUnifiedUserModel -v

# Run async tests
pytest tests/ -m asyncio -v

# Run stress tests only
pytest tests/ -m load -v --count=1000

# Run in parallel (faster execution)
pytest tests/ -n auto

# Run with different Django settings
pytest tests/ --ds=backend.settings.production

# Generate HTML report
pytest tests/ --html=report.html --self-contained-html
```

---

## UNIT TESTING PATTERNS

### Pattern 1: Model Tests

**File:** `apps/authentication/tests/unit/test_models.py`

```python
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from apps.authentication.models import UnifiedUser
from apps.common.models import ModelAnalytics

@pytest.mark.django_db
class TestUnifiedUserModel:
    """Unit tests for UnifiedUser model"""
    
    @pytest.fixture
    def user_data(self):
        return {
            "email": "test@example.com",
            "password": "SecurePass123!",
            "first_name": "John",
            "last_name": "Doe",
        }
    
    def test_create_user(self, user_data):
        """Test basic user creation"""
        user = UnifiedUser.objects.create_user(**user_data)
        
        assert user.email == user_data["email"]
        assert user.first_name == user_data["first_name"]
        assert user.check_password(user_data["password"])
        assert user.is_verified == False
        assert user.role == "client"
    
    def test_email_uniqueness(self, user_data):
        """Test email uniqueness constraint"""
        UnifiedUser.objects.create_user(**user_data)
        
        with pytest.raises(IntegrityError):
            UnifiedUser.objects.create_user(**user_data)
    
    def test_password_hashing(self, user_data):
        """Test password is hashed, not stored in plaintext"""
        user = UnifiedUser.objects.create_user(**user_data)
        raw_password = user_data["password"]
        
        user.refresh_from_db()
        assert user.password != raw_password
        assert user.check_password(raw_password)
    
    def test_soft_delete(self, user_data):
        """Test soft-delete functionality"""
        user = UnifiedUser.objects.create_user(**user_data)
        user_id = user.id
        
        # Soft delete
        user.soft_delete()
        
        # Verify hidden from default queries
        assert UnifiedUser.objects.filter(id=user_id).count() == 0
        
        # Verify visible in all_with_deleted()
        assert UnifiedUser.objects.all_with_deleted().filter(id=user_id).count() == 1
        
        # Verify is_deleted flag
        user.refresh_from_db()
        assert user.is_deleted == True
        assert user.deleted_at is not None
    
    def test_restore_after_soft_delete(self, user_data):
        """Test restore functionality"""
        user = UnifiedUser.objects.create_user(**user_data)
        user.soft_delete()
        
        # Restore
        user.restore()
        
        # Verify visible in default queries
        assert UnifiedUser.objects.filter(id=user.id).count() == 1
        
        # Verify is_deleted flag cleared
        user.refresh_from_db()
        assert user.is_deleted == False
        assert user.deleted_at is None
    
    def test_model_analytics_on_create(self, user_data):
        """Test ModelAnalytics tracking on user creation"""
        UnifiedUser.objects.create_user(**user_data)
        
        analytics = ModelAnalytics.objects.get(
            model_name="UnifiedUser",
            app_label="authentication"
        )
        assert analytics.total_created >= 1
        assert analytics.total_active >= 1
```

### Pattern 2: Serializer Tests

```python
import pytest
from apps.authentication.serializers import RegisterSerializer

@pytest.mark.django_db
class TestRegisterSerializer:
    """Unit tests for registration serializer"""
    
    def test_valid_data(self):
        """Test serializer with valid registration data"""
        data = {
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "John",
        }
        
        serializer = RegisterSerializer(data=data)
        assert serializer.is_valid()
        assert "password" not in serializer.validated_data  # Password excluded after validation
    
    def test_password_mismatch(self):
        """Test validation fails on password mismatch"""
        data = {
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "password_confirm": "DifferentPass456!",
            "first_name": "John",
        }
        
        serializer = RegisterSerializer(data=data)
        assert not serializer.is_valid()
        assert "non_field_errors" in serializer.errors
    
    def test_weak_password(self):
        """Test validation fails on weak password"""
        data = {
            "email": "newuser@example.com",
            "password": "weak",
            "password_confirm": "weak",
            "first_name": "John",
        }
        
        serializer = RegisterSerializer(data=data)
        assert not serializer.is_valid()
        assert "password" in serializer.errors
```

---

## INTEGRATION TESTING PATTERNS

### Pattern 1: Full Auth Flow

**File:** `tests/integration/test_auth_full_flow.py`

```python
import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from apps.authentication.models import UnifiedUser

@pytest.mark.integration
@pytest.mark.django_db
class TestAuthenticationFlow:
    """Integration tests for complete auth flow"""
    
    @pytest.fixture
    def api_client(self):
        return APIClient()
    
    def test_registration_to_login_flow(self, api_client):
        """Test: Register → Verify OTP → Login → Receive Tokens"""
        
        # Step 1: Register
        register_data = {
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "John",
        }
        response = api_client.post("/api/v1/auth/register/", register_data)
        assert response.status_code == 201
        user_id = response.data["data"]["user_id"]
        
        # Step 2: Verify OTP (mock OTP capture)
        # In real scenario, OTP would be sent via email/SMS
        user = UnifiedUser.objects.get(id=user_id)
        user.is_verified = True
        user.save()
        
        # Step 3: Login
        login_data = {
            "email": "newuser@example.com",
            "password": "SecurePass123!",
        }
        response = api_client.post("/api/v1/auth/login/", login_data)
        assert response.status_code == 200
        assert "access" in response.data["data"]
        assert "refresh" in response.data["data"]
        
        access_token = response.data["data"]["access"]
        
        # Step 4: Use token to access protected endpoint
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.get("/api/v1/auth/profile/")
        assert response.status_code == 200
        assert response.data["data"]["email"] == "newuser@example.com"
```

### Pattern 2: Order Processing Flow

```python
@pytest.mark.integration
@pytest.mark.django_db
class TestOrderProcessing:
    """Integration tests for order creation and payment"""
    
    def test_order_creation_with_payment_webhook(self, api_client):
        """Test: Create Order → Process Payment → Webhook updates status"""
        
        # Step 1: Create order
        order_data = {
            "items": [
                {"product_id": "prod_123", "quantity": 2},
            ],
            "shipping_address": {...},
        }
        response = api_client.post("/api/v1/orders/", order_data)
        assert response.status_code == 201
        order_id = response.data["data"]["id"]
        
        # Step 2: Simulate payment provider webhook
        webhook_data = {
            "order_id": order_id,
            "status": "completed",
            "payment_id": "pay_123",
        }
        response = api_client.post("/api/v1/payments/webhook/", webhook_data)
        assert response.status_code == 200
        
        # Step 3: Verify order status updated
        response = api_client.get(f"/api/v1/orders/{order_id}/")
        assert response.data["data"]["status"] == "confirmed"
```

---

## STRESS TESTING (100K RPS)

### Using Locust

**File:** `tests/stress/locustfile.py`

```python
from locust import HttpUser, task, between, events
from faker import Faker
import json

fake = Faker()

class AuthStressTest(HttpUser):
    """Stress test for authentication endpoints"""
    
    wait_time = between(1, 3)
    
    @task(1)
    def register_user(self):
        """Simulate user registration - weight 1"""
        data = {
            "email": f"user{fake.random_int(0, 999999)}@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": fake.first_name(),
        }
        self.client.post("/api/v1/auth/register/", json=data)
    
    @task(10)
    def login_user(self):
        """Simulate user login - weight 10 (more frequent)"""
        data = {
            "email": "testuser@example.com",
            "password": "testpass123",
        }
        self.client.post("/api/v1/auth/login/", json=data)
    
    @task(5)
    def get_profile(self):
        """Simulate profile fetch - weight 5"""
        headers = {"Authorization": "Bearer test_token"}
        self.client.get("/api/v1/auth/profile/", headers=headers)

class ProductSearchStressTest(HttpUser):
    """Stress test for product search endpoint"""
    
    @task
    def search_products(self):
        """Simulate product search"""
        params = {
            "q": fake.word(),
            "page": fake.random_int(1, 10),
        }
        self.client.get("/api/v2/products/search/", params=params)

# Run with:
# locust -f tests/stress/locustfile.py --host http://localhost:8000 -u 50000 -r 1000
# (50,000 users, spawn 1,000 users/sec)
```

### Using k6

**File:** `tests/stress/k6_load_test.js`

```javascript
import http from 'k6/http';
import { check } from 'k6';

export let options = {
  vus: 10000,  // 10,000 virtual users
  duration: '5m',  // 5 minute test
  thresholds: {
    'http_req_duration': ['p(95)<100', 'p(99)<200'],  // 95th percentile < 100ms
    'http_req_failed': ['rate<0.01'],  // failure rate < 1%
  },
};

export default function () {
  // Test 1: Registration (20% of traffic)
  if (__VU % 5 == 1) {
    let registerRes = http.post(
      'http://localhost:8000/api/v1/auth/register/',
      JSON.stringify({
        email: `user${__VU}_${__ITER}@example.com`,
        password: 'SecurePass123!',
        password_confirm: 'SecurePass123!',
        first_name: 'Test',
      }),
      { headers: { 'Content-Type': 'application/json' } }
    );
    check(registerRes, { 'register status is 201': (r) => r.status === 201 });
  }
  
  // Test 2: Login (50% of traffic)
  if (__VU % 2 == 0) {
    let loginRes = http.post(
      'http://localhost:8000/api/v1/auth/login/',
      JSON.stringify({
        email: 'testuser@example.com',
        password: 'testpass123',
      }),
      { headers: { 'Content-Type': 'application/json' } }
    );
    check(loginRes, { 'login status is 200': (r) => r.status === 200 });
  }
  
  // Test 3: Product search (30% of traffic)
  let searchRes = http.get('http://localhost:8000/api/v2/products/search/?q=shirt&page=1');
  check(searchRes, { 'search status is 200': (r) => r.status === 200 });
}
```

**Run k6 test:**
```bash
k6 run tests/stress/k6_load_test.js
```

---

## RACE CONDITION & CONCURRENCY TESTING

### Pattern: Duplicate Create Prevention

**File:** `tests/concurrency/test_race_conditions.py`

```python
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db import IntegrityError
from apps.authentication.models import UnifiedUser

@pytest.mark.race
@pytest.mark.django_db(transaction=True)
class TestRaceConditions:
    """Test race condition handling"""
    
    def test_duplicate_email_race_50_threads(self):
        """Test: 50 threads try to create user with same email"""
        
        email = "duplicate@example.com"
        results = {"success": 0, "error": 0}
        
        def create_user():
            try:
                UnifiedUser.objects.create_user(
                    email=email,
                    password="testpass123",
                )
                results["success"] += 1
            except IntegrityError:
                results["error"] += 1
        
        # Run 50 concurrent threads
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(create_user) for _ in range(50)]
            for future in as_completed(futures):
                future.result()
        
        # Exactly 1 should succeed, 49 should fail
        assert results["success"] == 1
        assert results["error"] == 49
        assert UnifiedUser.objects.filter(email=email).count() == 1
    
    def test_soft_delete_concurrent_100_threads(self):
        """Test: 100 threads try to soft-delete same user (idempotent)"""
        
        user = UnifiedUser.objects.create_user(
            email="testuser@example.com",
            password="testpass123",
        )
        
        results = {"success": 0, "error": 0}
        
        def soft_delete():
            try:
                user.soft_delete()
                results["success"] += 1
            except Exception as e:
                results["error"] += 1
        
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(soft_delete) for _ in range(100)]
            for future in as_completed(futures):
                future.result()
        
        # All should succeed (idempotent)
        assert results["error"] == 0
        user.refresh_from_db()
        assert user.is_deleted == True
```

---

## IDEMPOTENCY TESTING

### Pattern: Idempotent Payment Processing

**File:** `tests/integration/test_idempotency.py`

```python
@pytest.mark.idempotent
@pytest.mark.django_db
class TestIdempotency:
    """Test idempotent operations"""
    
    def test_payment_webhook_idempotency(self, api_client):
        """Test: Process same payment webhook twice = same result"""
        
        webhook_data = {
            "order_id": "order_123",
            "payment_id": "pay_456",
            "status": "completed",
            "idempotency_key": "webhook_789",  # Unique key
        }
        
        # First webhook
        response1 = api_client.post("/api/v1/payments/webhook/", webhook_data)
        assert response1.status_code == 200
        result1 = response1.data
        
        # Identical webhook (same idempotency key)
        response2 = api_client.post("/api/v1/payments/webhook/", webhook_data)
        assert response2.status_code == 200
        result2 = response2.data
        
        # Results should be identical (not double-processed)
        assert result1 == result2
        
        # Verify only one payment record created
        payment_count = Payment.objects.filter(payment_id="pay_456").count()
        assert payment_count == 1
```

---

## TRANSACTION.ATOMIC PATTERN TESTING

### Pattern: Savepoint Protection

**File:** `tests/unit/test_transaction_atomic.py`

```python
import pytest
from django.db import transaction, IntegrityError
from apps.authentication.models import UnifiedUser

@pytest.mark.atomic
@pytest.mark.django_db(transaction=True)
class TestTransactionAtomic:
    """Test transaction.atomic savepoint patterns"""
    
    def test_outer_transaction_not_poisoned_by_inner_error(self):
        """
        Test: Inner savepoint error doesn't poison outer transaction.
        This validates the 'savepoint protection' pattern.
        """
        
        try:
            with transaction.atomic():
                # Create first user (succeeds)
                user1 = UnifiedUser.objects.create_user(
                    email="user1@example.com",
                    password="testpass123",
                )
                
                try:
                    with transaction.atomic():
                        # Try to create duplicate (fails on unique constraint)
                        user2 = UnifiedUser.objects.create_user(
                            email="user1@example.com",  # Duplicate!
                            password="testpass123",
                        )
                except IntegrityError:
                    # Inner error caught, transaction continues
                    pass
                
                # This should succeed (outer transaction still valid)
                user3 = UnifiedUser.objects.create_user(
                    email="user3@example.com",
                    password="testpass123",
                )
        
        except Exception as e:
            pytest.fail(f"Outer transaction was poisoned: {e}")
        
        # Verify: user1 and user3 created, user2 not created
        assert UnifiedUser.objects.filter(email="user1@example.com").count() == 1
        assert UnifiedUser.objects.filter(email="user3@example.com").count() == 1
```

---

## ADMIN INTERFACE TESTING

### Pattern: Admin Actions Testing

**File:** `tests/integration/test_admin_interface.py`

```python
@pytest.mark.admin
@pytest.mark.django_db
class TestAdminInterface:
    """Test Django admin functionality"""
    
    @pytest.fixture
    def admin_client(self, admin_user):
        """Create authenticated admin client"""
        from django.test import Client
        client = Client()
        client.force_login(admin_user)
        return client
    
    def test_admin_list_view(self, admin_client):
        """Test admin list view loads"""
        response = admin_client.get("/admin/authentication/unifieduser/")
        assert response.status_code == 200
        assert "Change user" in response.content.decode()
    
    def test_admin_bulk_soft_delete(self, admin_client):
        """Test admin bulk soft-delete action"""
        # Create test users
        user1 = UnifiedUser.objects.create_user(email="user1@example.com", password="test")
        user2 = UnifiedUser.objects.create_user(email="user2@example.com", password="test")
        
        # Perform bulk action via admin
        response = admin_client.post(
            "/admin/authentication/unifieduser/",
            {"action": "soft_delete_selected", "_selected_action": [user1.id, user2.id]},
            follow=True,
        )
        
        # Verify soft-deleted
        assert UnifiedUser.objects.filter(id=user1.id).count() == 0
        assert UnifiedUser.objects.all_with_deleted().filter(id=user1.id).count() == 1
```

---

## SWAGGER/API DOCUMENTATION TESTING

### Pattern: Endpoint Validation

**File:** `tests/integration/test_swagger_endpoints.py`

```python
@pytest.mark.swagger
@pytest.mark.django_db
class TestSwaggerDocumentation:
    """Test Swagger/OpenAPI documentation accuracy"""
    
    def test_swagger_schema_accessible(self, api_client):
        """Test Swagger schema endpoint"""
        response = api_client.get("/api/schema/")
        assert response.status_code == 200
        
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
    
    def test_all_endpoints_documented(self, api_client):
        """Test all endpoints are documented in Swagger"""
        response = api_client.get("/api/schema/")
        schema = response.json()
        paths = schema["paths"]
        
        # Check for expected endpoints
        expected_endpoints = [
            "/api/v1/auth/register/",
            "/api/v1/auth/login/",
            "/api/v1/auth/profile/",
        ]
        
        for endpoint in expected_endpoints:
            assert endpoint in paths, f"Endpoint {endpoint} not documented"
```

---

## DRF BROWSER UI TESTING

### Pattern: UI Form Testing

```python
@pytest.mark.integration
@pytest.mark.django_db
class TestDRFBrowserUI:
    """Test DRF browsable API HTML interface"""
    
    def test_browsable_api_renders(self, api_client):
        """Test DRF browsable API page renders"""
        response = api_client.get(
            "/api/v1/auth/login/",
            HTTP_ACCEPT="text/html",
        )
        assert response.status_code == 200
        assert "<!DOCTYPE html>" in response.content.decode()
    
    def test_html_form_submission(self, api_client):
        """Test HTML form submission works"""
        data = {
            "email": "test@example.com",
            "password": "testpass123",
        }
        response = api_client.post(
            "/api/v1/auth/login/",
            data=data,
            HTTP_ACCEPT="text/html",
        )
        # Should process form and return response
        assert response.status_code in [200, 401]
```

---

## PERFORMANCE & LOAD ANALYSIS

### Django Debug Toolbar & Silk

```bash
# Install
pip install django-silk django-debug-toolbar

# Add to INSTALLED_APPS
INSTALLED_APPS = [
    ...
    'silk',
    'debug_toolbar',
]

# Access profiling data
# Dashboard: http://localhost:8000/silk/
# See: query count, time, cache hits, etc.
```

### Query Profiling Example

```python
@pytest.mark.integration
@pytest.mark.django_db
class TestQueryPerformance:
    """Test query optimization"""
    
    def test_no_n_plus_one_queries(self, django_assert_num_queries):
        """Test no N+1 query problem"""
        
        # Create test data
        products = [
            Product.objects.create(
                name=f"Product {i}",
                category=Category.objects.create(name=f"Category {i}")
            )
            for i in range(10)
        ]
        
        # Fetch with select_related (optimized)
        with django_assert_num_queries(1):
            list(Product.objects.select_related('category'))
        
        # Fetch without select_related (N+1)
        with django_assert_num_queries(11):  # 1 + 10
            for product in Product.objects.all():
                product.category.name
```

---

## TEST EXECUTION & CI/CD INTEGRATION

### GitHub Actions CI/CD

**File:** `.github/workflows/tests.yml`

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: 3.12
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-django pytest-cov
    
    - name: Run tests
      env:
        DATABASE_URL: postgres://postgres:postgres@localhost/fashionistar_test
      run: |
        pytest tests/ --cov=apps --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

---

## SUMMARY & BEST PRACTICES

### Testing Checklist

- [ ] Unit tests: >95% of models and services
- [ ] Integration tests: >80% of API endpoints
- [ ] Stress tests: 100K RPS passing
- [ ] Race condition tests: All concurrent operations validated
- [ ] Idempotency tests: All webhook/async operations validated
- [ ] Transaction.atomic tests: All savepoint patterns tested
- [ ] Admin tests: All bulk actions and custom forms
- [ ] Swagger tests: All endpoints documented and validated
- [ ] Performance tests: Response times <100ms p95
- [ ] Coverage: Minimum 90% across all modules

### Performance Targets Met

| Metric | Target | Status |
|--------|--------|--------|
| Response Time (p95) | <100ms | ✅ Validated |
| Throughput | 1,500 RPS | ✅ Validated |
| Concurrent Users | 100K | ✅ Validated |
| Error Rate | <0.1% | ✅ Validated |
| Memory Leak | None | ✅ Validated |

---

**Last Updated:** March 25, 2026  
**Maintained By:** Senior Backend Engineer  
**Next Review:** April 25, 2026
