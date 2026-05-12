# vendor/tests/conftest.py
"""
vendor app — Test fixtures
===========================
Fixtures for testing vendor registration, shop management,
product listings, withdrawals, and vendor analytics.
"""
import pytest
from unittest.mock import patch


@pytest.fixture
@pytest.mark.django_db
def vendor_user_legacy(db):
    """A vendor (legacy userauths.User with associated Vendor profile)."""
    from userauths.models import User
    user = User.objects.create_user(
        username='testvendor',
        email='vendor@fashionistar-test.io',
        password='VendorPass!456',
        vendor=True,  # if field exists
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
@pytest.mark.django_db
def vendor_profile(db, vendor_user_legacy):
    """Get or create the Vendor profile for the vendor user."""
    try:
        from vendor.models import Vendor
        vendor, _ = Vendor.objects.get_or_create(user=vendor_user_legacy)
        return vendor
    except Exception:
        return None


@pytest.fixture
def mock_paystack_transfer():
    """Mock Paystack transfer for vendor withdrawal tests."""
    with patch('Paystack_Webhoook_Prod.VendorWithdrawView.initiate_transfer') as mock_transfer:
        mock_transfer.return_value = {
            'status': True,
            'data': {
                'status': 'pending',
                'transfer_code': 'TRF_test123',
                'amount': 100000,
            },
        }
        yield mock_transfer
