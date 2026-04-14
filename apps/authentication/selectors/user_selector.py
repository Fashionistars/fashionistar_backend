# apps/authentication/selectors/user_selector.py
"""
User Selector — Read-only QuerySet logic for UnifiedUser.

Architecture rule: No direct ORM calls in views. Use selectors for
all read operations, services for writes.

Usage:
    from apps.authentication.selectors import UserSelector

    user = UserSelector.get_by_email('test@fashionistar.io')
    if not user:
        raise Http404
"""
from __future__ import annotations

import logging
from typing import Optional

from django.db.models import Q, QuerySet

from apps.authentication.models import UnifiedUser
from apps.common.selectors import BaseSelector

logger = logging.getLogger(__name__)


class UserSelector(BaseSelector):
    """
    Read-only queryset logic for UnifiedUser.

    All methods return QuerySets or model instances.
    None is returned (not raised) for missing single objects —
    let the VIEW decide whether a missing user is a 404 or a 200.
    """

    model = UnifiedUser

    # ─────────────────────────────────────────────────────────────────
    # Lookup Methods
    # ─────────────────────────────────────────────────────────────────

    @classmethod
    def get_by_email(cls, email: str) -> Optional[UnifiedUser]:
        """
        Case-insensitive email lookup.

        Args:
            email: Email address to search.

        Returns:
            Optional[UnifiedUser]: User or None.
        """
        return cls.model.objects.filter(email__iexact=email.strip()).first()

    @classmethod
    def get_by_phone(cls, phone: str) -> Optional[UnifiedUser]:
        """
        Phone number lookup (E.164 format).

        Args:
            phone: Phone number in E.164 format (+234...).

        Returns:
            Optional[UnifiedUser]: User or None.
        """
        return cls.model.objects.filter(phone=phone).first()

    @classmethod
    def get_by_email_or_phone(cls, identifier: str) -> Optional[UnifiedUser]:
        """
        Try email then phone lookup from a single string.

        Args:
            identifier: Email address or phone number.

        Returns:
            Optional[UnifiedUser]: User or None.
        """
        return cls.model.objects.filter(
            Q(email=identifier) if "@" in identifier else Q(phone=identifier)
        ).first()

    @classmethod
    def get_by_id_safe(cls, user_id) -> Optional[UnifiedUser]:
        """
        UUID-safe get_by_id — swallows ValueError for malformed UUIDs.

        Args:
            user_id: User UUID.

        Returns:
            Optional[UnifiedUser]: User or None.
        """
        try:
            return cls.model.objects.only(
                "id",
                "email",
                "phone",
                "role",
                "is_active",
                "is_verified",
                "auth_provider",
            ).get(pk=user_id)
        except (cls.model.DoesNotExist, ValueError, TypeError):
            return None

    # ─────────────────────────────────────────────────────────────────
    # Role-based Querysets
    # ─────────────────────────────────────────────────────────────────

    @classmethod
    def get_vendors(cls) -> QuerySet:
        """All active, verified vendor accounts."""
        return cls.model.objects.filter(
            role="vendor", is_active=True, is_verified=True
        ).order_by("-date_joined")

    @classmethod
    def get_clients(cls) -> QuerySet:
        """All active client accounts."""
        return cls.model.objects.filter(role="client", is_active=True).order_by(
            "-date_joined"
        )

    @classmethod
    def get_active_staff(cls) -> QuerySet:
        """All active staff/admin accounts."""
        return cls.model.objects.filter(
            is_active=True, role__in=["admin", "super_admin", "staff", "moderator"]
        )

    @classmethod
    def get_unverified(cls) -> QuerySet:
        """Users who have registered but not yet verified OTP."""
        return cls.model.objects.filter(is_active=False, is_verified=False)

    # ─────────────────────────────────────────────────────────────────
    # Async equivalents (for Ninja async_views.py)
    # ─────────────────────────────────────────────────────────────────

    @classmethod
    async def aget_by_email(cls, email: str) -> Optional[UnifiedUser]:
        """Async email lookup."""
        try:
            return await cls.model.objects.aget(email__iexact=email.strip())
        except cls.model.DoesNotExist:
            return None

    @classmethod
    async def aget_by_phone(cls, phone: str) -> Optional[UnifiedUser]:
        """Async phone lookup."""
        try:
            return await cls.model.objects.aget(phone=phone)
        except cls.model.DoesNotExist:
            return None

    @classmethod
    async def aget_by_email_or_phone(cls, identifier: str) -> Optional[UnifiedUser]:
        """Async email-or-phone lookup."""
        try:
            return await cls.model.objects.aget(
                Q(email=identifier) if "@" in identifier else Q(phone=identifier)
            )
        except cls.model.DoesNotExist:
            return None
