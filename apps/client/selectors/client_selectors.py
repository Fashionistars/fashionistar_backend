# apps/client/selectors/client_selectors.py
"""
Client Domain Selectors — Read-only data fetching layer.

Selectors encapsulate all database read queries for the client domain.
They are imported by API views, never by services (services own writes).

All public functions are synchronous; async variants (prefixed `a`) are
provided for Ninja endpoints.
"""
import logging
from typing import Any

from django.db.models import QuerySet

logger = logging.getLogger(__name__)


def get_client_profile_or_none(user) -> "ClientProfile | None":  # noqa: F821
    """
    Return the ClientProfile for `user` or None if it doesn't exist.
    """
    from apps.client.models import ClientProfile
    try:
        return ClientProfile.objects.select_related("user").get(user=user)
    except ClientProfile.DoesNotExist:
        return None


async def aget_client_profile_or_none(user) -> "ClientProfile | None":  # noqa: F821
    """Async variant of get_client_profile_or_none."""
    from apps.client.models import ClientProfile
    try:
        return await ClientProfile.objects.select_related("user").aget(user=user)
    except ClientProfile.DoesNotExist:
        return None


def list_client_addresses(user) -> "QuerySet":
    """
    Return all active (non-soft-deleted) addresses for `user`,
    ordered: default first, then by creation date descending.
    """
    from apps.client.models import ClientProfile, ClientAddress
    try:
        profile = ClientProfile.objects.get(user=user)
        return ClientAddress.objects.filter(
            client=profile, is_deleted=False
        ).order_by("-is_default", "-created_at")
    except Exception:
        from apps.client.models import ClientAddress
        return ClientAddress.objects.none()


def get_client_stats(user) -> dict[str, Any]:
    """
    Return lightweight stats dict for the client.
    Used by JWT token serializer to embed quick data.
    """
    try:
        from apps.client.models import ClientProfile
        profile = ClientProfile.objects.values(
            "total_orders",
            "total_spent_ngn",
            "is_profile_complete",
            "preferred_size",
        ).get(user=user)
        return profile
    except Exception:
        return {
            "total_orders": 0,
            "total_spent_ngn": 0,
            "is_profile_complete": False,
            "preferred_size": "",
        }
