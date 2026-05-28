import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework_simplejwt.tokens import AccessToken


def make_user(**overrides):
    User = get_user_model()
    seq = overrides.pop("seq", "1")
    defaults = {
        "email": f"admin-platform-{seq}@fashionistar.test",
        "password": "AdminPlatform!123",
        "role": "client",
        "is_active": True,
        "is_verified": True,
        "is_staff": False,
    }
    defaults.update(overrides)
    password = defaults.pop("password")
    return User.objects.create_user(password=password, **defaults)


@pytest.mark.django_db
def test_admin_dashboard_kpi_requires_admin_bearer_access():
    client = Client()
    response = client.get("/api/v1/admin_backend/dashboard/kpi/")
    assert response.status_code in {401, 403}


@pytest.mark.django_db
def test_admin_dashboard_kpi_denies_verified_non_admin_users():
    user = make_user(seq="2", role="client")
    token = str(AccessToken.for_user(user))
    client = Client(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = client.get("/api/v1/admin_backend/dashboard/kpi/")

    assert response.status_code in {401, 403}


@pytest.mark.django_db
def test_admin_dashboard_kpi_allows_admin_users():
    admin_user = make_user(seq="3", role="admin", is_staff=True, is_active=True)
    token = str(AccessToken.for_user(admin_user))
    client = Client(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = client.get("/api/v1/admin_backend/dashboard/kpi/")

    assert response.status_code == 200
    payload = response.json()
    assert "total_users" in payload
    assert "generated_at" in payload


@pytest.mark.django_db
def test_auth_suspend_endpoint_uses_shared_admin_permission_and_service():
    admin_user = make_user(seq="4", role="admin", is_staff=True, is_active=True)
    target_user = make_user(seq="5", role="client", is_active=True)
    token = str(AccessToken.for_user(admin_user))
    client = Client(
        HTTP_AUTHORIZATION=f"Bearer {token}",
        CONTENT_TYPE="application/json",
    )

    response = client.post(
        f"/api/v1/admin_backend/auth/users/{target_user.pk}/suspend/",
        data={"reason": "Fraud review"},
    )

    assert response.status_code == 200
    target_user.refresh_from_db()
    assert target_user.is_active is False


@pytest.mark.django_db
def test_auth_role_update_requires_superuser():
    admin_user = make_user(seq="6", role="admin", is_staff=True, is_active=True)
    target_user = make_user(seq="7", role="client", is_active=True)
    token = str(AccessToken.for_user(admin_user))
    client = Client(
        HTTP_AUTHORIZATION=f"Bearer {token}",
        CONTENT_TYPE="application/json",
    )

    response = client.post(
        f"/api/v1/admin_backend/auth/users/{target_user.pk}/update-role/",
        data={"role": "support"},
    )

    assert response.status_code in {401, 403}
