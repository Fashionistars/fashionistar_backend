# apps/common/selectors.py
"""
Base Selector Pattern — Fashionistar Architecture §6.5

Rules (non-negotiable):
  - Selectors encapsulate READ-ONLY QuerySet logic
  - Never accept HttpRequest objects as parameters
  - Always use select_related / prefetch_related to prevent N+1 queries
  - Return QuerySets or typed dicts (never HttpResponse)
  - Views call Services for writes; Views call Selectors for reads

Usage example:
    class ProductSelector(BaseSelector):
        model = Product

        @classmethod
        def get_published(cls) -> QuerySet:
            return cls.get_all_active().select_related('category', 'brand')
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Type, TypeVar

from django.db.models import Model, QuerySet

logger = logging.getLogger('application')

T = TypeVar('T', bound=Model)


class BaseSelector:
    """
    Base class providing common, reusable queryset helpers.

    All domain selectors inherit from this class and set `model`.

    Attributes:
        model (Type[Model]): The Django model class this selector operates on.
    """

    model: Type[T]  # Subclasses MUST define this

    # ─────────────────────────────────────────────────────────────────
    # Sync Methods — use in DRF views (sync_views.py)
    # ─────────────────────────────────────────────────────────────────

    @classmethod
    def get_by_id(cls, pk: Any) -> Optional[T]:
        """
        Fetch a single object by primary key.
        Returns None if not found (no exception raised).

        Args:
            pk: Primary key value (UUID, int, str).

        Returns:
            Optional[T]: Model instance or None.
        """
        try:
            return cls.model.objects.get(pk=pk)
        except cls.model.DoesNotExist:
            return None

    @classmethod
    def get_by_id_or_raise(cls, pk: Any) -> T:
        """
        Fetch a single object by PK. Raises DoesNotExist if not found.

        Use this when a missing object is genuinely exceptional.

        Args:
            pk: Primary key value.

        Returns:
            T: Model instance.

        Raises:
            Model.DoesNotExist: If the object does not exist.
        """
        return cls.model.objects.get(pk=pk)

    @classmethod
    def get_all_active(cls) -> QuerySet:
        """
        Return all active records.
        Requires `is_active` field on the model.

        Returns:
            QuerySet: Active records.
        """
        return cls.model.objects.filter(is_active=True)

    @classmethod
    def get_all(cls) -> QuerySet:
        """Return all records (no filtering)."""
        return cls.model.objects.all()

    @classmethod
    def exists(cls, **kwargs: Any) -> bool:
        """
        Efficient existence check (SELECT 1 WHERE ... LIMIT 1).

        Args:
            **kwargs: Filter keyword arguments.

        Returns:
            bool: True if any matching record exists.
        """
        return cls.model.objects.filter(**kwargs).exists()

    @classmethod
    def count(cls, **kwargs: Any) -> int:
        """
        Efficient count query.

        Args:
            **kwargs: Filter keyword arguments.

        Returns:
            int: Number of matching records.
        """
        return cls.model.objects.filter(**kwargs).count()

    # ─────────────────────────────────────────────────────────────────
    # Async Methods — use in Ninja async_views.py
    # ─────────────────────────────────────────────────────────────────

    @classmethod
    async def aget_by_id(cls, pk: Any) -> Optional[T]:
        """
        Async version of get_by_id — use in async views / Ninja endpoints.

        Args:
            pk: Primary key value.

        Returns:
            Optional[T]: Model instance or None.
        """
        try:
            return await cls.model.objects.aget(pk=pk)
        except cls.model.DoesNotExist:
            return None

    @classmethod
    async def aget_by_id_or_raise(cls, pk: Any) -> T:
        """
        Async get by PK — raises DoesNotExist if not found.

        Args:
            pk: Primary key value.

        Returns:
            T: Model instance.

        Raises:
            Model.DoesNotExist: If the object does not exist.
        """
        return await cls.model.objects.aget(pk=pk)

    @classmethod
    async def aexists(cls, **kwargs: Any) -> bool:
        """
        Async existence check.

        Args:
            **kwargs: Filter keyword arguments.

        Returns:
            bool: True if matching record exists.
        """
        return await cls.model.objects.filter(**kwargs).aexists()

    @classmethod
    async def acount(cls, **kwargs: Any) -> int:
        """
        Async count query.

        Args:
            **kwargs: Filter keyword arguments.

        Returns:
            int: Number of matching records.
        """
        return await cls.model.objects.filter(**kwargs).acount()
