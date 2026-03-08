# apps/authentication/tests/factories.py
"""
apps.authentication — Factory-Boy factory classes.

Usage:
    from apps.authentication.tests.factories import (
        UnifiedUserFactory, OTPTokenFactory, VerifiedUserFactory
    )
    user = UnifiedUserFactory.create()
    otp = OTPTokenFactory(user=user, otp_code='123456')
"""
import factory
from factory.django import DjangoModelFactory
import uuid
from django.utils import timezone


class UnifiedUserFactory(DjangoModelFactory):
    """
    Inactive, unverified user — the default pre-OTP registration state.
    """
    class Meta:
        model = 'authentication.UnifiedUser'
        django_get_or_create = ('email',)

    id = factory.LazyFunction(uuid.uuid4)
    email = factory.Sequence(lambda n: f'authtest{n}@fashionistar-test.io')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    role = 'client'
    is_active = False
    is_verified = False
    is_staff = False

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        manager = cls._get_manager(model_class)
        password = kwargs.pop('password', 'AuthFactory!789')
        if hasattr(manager, 'create_user'):
            user = manager.create_user(password=password, **kwargs)
            return user
        return super()._create(model_class, *args, **kwargs)


class VerifiedUserFactory(UnifiedUserFactory):
    """Active verified user (post-OTP)."""
    is_active = True
    is_verified = True
    email = factory.Sequence(lambda n: f'verified{n}@fashionistar-test.io')


class VendorUserFactory(VerifiedUserFactory):
    """Verified vendor."""
    role = 'vendor'
    email = factory.Sequence(lambda n: f'vendor{n}@fashionistar-test.io')


class OTPTokenFactory(DjangoModelFactory):
    """
    OTP token for a user.

    Usage:
        token = OTPTokenFactory(user=user, otp_code='999999')
    """
    class Meta:
        model = 'authentication.OTPToken'

    user = factory.SubFactory(UnifiedUserFactory)
    otp_code = factory.Sequence(lambda n: str(100000 + n))
    is_used = False
    created_at = factory.LazyFunction(timezone.now)
