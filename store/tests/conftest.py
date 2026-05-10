# store/tests/conftest.py
"""
store app — Test fixtures
==========================
Fixtures for testing the store app:
  - Products, Categories, Brands, Reviews, Coupons,
    CartOrders, CartOrderItems, Cart

All fixtures use factory-boy. External service calls (images, Cloudinary)
are mocked to prevent HTTP in test runs.
"""
import pytest
from unittest.mock import patch


@pytest.fixture
def mock_cloudinary_upload():
    """Prevent Cloudinary upload calls during product image tests."""
    with patch('cloudinary.uploader.upload') as mock_upload:
        mock_upload.return_value = {
            'public_id': 'test/product_image',
            'secure_url': 'https://res.cloudinary.com/test/image/upload/v1/test/product_image.jpg',
        }
        yield mock_upload


@pytest.fixture
@pytest.mark.django_db
def store_user(db):
    """A verified user who can interact with the store."""
    from userauths.models import User
    user = User.objects.create_user(
        username='storeuser',
        email='store@fashionistar-test.io',
        password='StoreTest!123',
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
@pytest.mark.django_db
def store_vendor(db, store_user):
    """A vendor user with a store profile."""
    from vendor.models import Vendor
    vendor, _ = Vendor.objects.get_or_create(user=store_user)
    return vendor
