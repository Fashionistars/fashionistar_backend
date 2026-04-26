import pytest
from django.urls import reverse
from rest_framework import status
from apps.authentication.models import UnifiedUser
from tests.factories import UserFactory

@pytest.mark.django_db
class TestAdminRolesAndPermissions:
    """
    Validation of RBAC (Role-Based Access Control) for Fashionistar.
    Ensures that Vendors, Clients, and Admins cannot bypass their respective silos.
    """

    @pytest.fixture
    def admin_user(self, db):
        return UserFactory(role='admin', is_staff=True, is_superuser=True)

    @pytest.fixture
    def vendor_user(self, db):
        return UserFactory(role='vendor', is_verified=True)

    @pytest.fixture
    def client_user(self, db):
        return UserFactory(role='client', is_verified=True)

    def test_vendor_cannot_access_client_wishlist(self, api_client, vendor_user, client_user):
        """Vendors should be blocked from client-only endpoints."""
        api_client.force_authenticate(user=vendor_user)
        url = reverse('client:wishlist') 
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_client_cannot_access_vendor_payout(self, api_client, client_user):
        """Clients should be blocked from vendor-only endpoints."""
        api_client.force_authenticate(user=client_user)
        url = reverse('vendor_domain:payout') 
        response = api_client.post(url, {})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_has_god_mode_access(self, api_client, admin_user):
        """Admins (staff) should bypass role checks if configured correctly."""
        api_client.force_authenticate(user=admin_user)
        url = reverse('catalog:category-list') 
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_unauthenticated_user_access_denied(self, api_client):
        """Secure by default: public access restricted to AllowAny endpoints."""
        url = reverse('vendor_domain:profile')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
