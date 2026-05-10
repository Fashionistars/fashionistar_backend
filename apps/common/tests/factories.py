# apps/common/tests/factories.py
"""
apps.common — Factory-Boy factories for common app models.

These factories build AuditLog, BaseModel subclass instances,
and other common infrastructure models used across tests.

Usage:
    from apps.common.tests.factories import AuditLogFactory
    entry = AuditLogFactory()
"""
import factory
from factory.django import DjangoModelFactory
import uuid
from django.utils import timezone


class BaseModelFactory(DjangoModelFactory):
    """
    Abstract factory for all models inheriting from apps.common.models.BaseModel.
    Provides created_at, updated_at, is_active defaults.
    """
    class Meta:
        abstract = True

    id = factory.LazyFunction(uuid.uuid4)
    is_active = True
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)
