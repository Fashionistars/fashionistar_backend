# customer/tests/conftest.py
"""
customer app — Test fixtures
=============================
Fixtures for testing customer orders, wishlist,
wallet balance, reviews, and profile views.
"""
import pytest
from decimal import Decimal


@pytest.fixture
@pytest.mark.django_db
def customer_user(db):
    """A regular customer user (legacy userauths.User)."""
    from userauths.models import User
    user = User.objects.create_user(
        username='customer_test',
        email='customer@fashionistar-test.io',
        password='CustomerPass!234',
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
@pytest.mark.django_db
def customer_profile(db, customer_user):
    """Customer's UserProfile if one exists."""
    try:
        from userauths.models import Profile
        profile, _ = Profile.objects.get_or_create(user=customer_user)
        return profile
    except Exception:
        return None


@pytest.fixture
def mock_paystack_verify():
    """Mock Paystack payment verification so tests don't hit the API."""
    from unittest.mock import patch
    with patch('Paystack_Webhoook_Prod.deposit.verify_payment') as mock_verify:
        mock_verify.return_value = {
            'status': True,
            'data': {
                'status': 'success',
                'amount': 500000,  # ₦5,000 in kobo
                'reference': 'test_ref_123',
                'customer': {'email': 'customer@fashionistar-test.io'},
            },
        }
        yield mock_verify
