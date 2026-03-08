# tests/factories.py
"""
FASHIONISTAR — Global Factory-Boy Factory Classes
==================================================
One canonical set of factory classes for all tests.

Pattern:
  - Each factory maps to a model
  - Factories use Faker for realistic data
  - Sub-factories (LazyAttribute, SubFactory) for related models
  - All factories default to safe test values

Usage:
    from tests.factories import UnifiedUserFactory, UserProfileFactory

    user = UnifiedUserFactory()                            # unsaved instance
    user = UnifiedUserFactory.create()                     # saved to DB
    users = UnifiedUserFactory.create_batch(5)             # 5 users
    vendor = UnifiedUserFactory(role='vendor')             # specific role
    verified = UnifiedUserFactory(is_active=True, is_verified=True)

Per-app factories (app-specific) are in:
    apps/<app>/tests/factories.py
    <legacy_app>/tests/factories.py
"""
import factory
from factory.django import DjangoModelFactory
from factory import fuzzy
import uuid


# =============================================================================
#  USER FACTORIES (apps.authentication.UnifiedUser)
# =============================================================================

class UnifiedUserFactory(DjangoModelFactory):
    """
    Factory for apps.authentication.models.UnifiedUser.
    Creates an inactive, unverified user by default (pre-OTP state).
    """
    class Meta:
        model = 'authentication.UnifiedUser'
        django_get_or_create = ('email',)

    id = factory.LazyFunction(uuid.uuid4)
    email = factory.Sequence(lambda n: f'testuser{n}@fashionistar-test.io')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    password = factory.PostGenerationMethodCall('set_password', 'SecurePass!234')
    role = 'client'
    is_active = False       # Pre-OTP state — must verify before login
    is_verified = False
    is_staff = False
    is_superuser = False

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Use the manager's create_user to ensure password hashing."""
        manager = cls._get_manager(model_class)
        if hasattr(manager, 'create_user'):
            password = kwargs.pop('password', 'SecurePass!234')
            user = manager.create_user(**kwargs)
            user.set_password(password)
            user.save()
            return user
        return super()._create(model_class, *args, **kwargs)


class VerifiedUserFactory(UnifiedUserFactory):
    """Already verified and active user — can log in immediately."""
    is_active = True
    is_verified = True


class VendorUserFactory(VerifiedUserFactory):
    """Verified vendor user."""
    role = 'vendor'
    email = factory.Sequence(lambda n: f'vendor{n}@fashionistar-test.io')


class CustomerUserFactory(VerifiedUserFactory):
    """Verified customer user."""
    role = 'client'
    email = factory.Sequence(lambda n: f'customer{n}@fashionistar-test.io')


class AdminUserFactory(VerifiedUserFactory):
    """Admin/staff user."""
    role = 'admin'
    is_staff = True
    email = factory.Sequence(lambda n: f'admin{n}@fashionistar-test.io')


# =============================================================================
#  LEGACY USER FACTORY (userauths.User — legacy model)
# =============================================================================

class LegacyUserFactory(DjangoModelFactory):
    """
    Factory for userauths.User (legacy Django auth user).
    Used in tests for store, customer, vendor that use the old auth model.
    """
    class Meta:
        model = 'userauths.User'
        django_get_or_create = ('email',)

    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.Sequence(lambda n: f'legacy{n}@fashionistar-test.io')
    password = factory.PostGenerationMethodCall('set_password', 'LegacyPass!456')
    is_active = True
