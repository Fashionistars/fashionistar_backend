# apps/client/selectors/client_selectors.py
"""
Client Domain Selectors — Read-only data fetching layer.

Architecture Rules (NON-NEGOTIABLE):
  ─ Selectors NEVER mutate data. All mutations live in services/.
  ─ Sync selectors (no prefix) → used in DRF sync views / Django admin.
  ─ Async selectors (prefix `a`) → used in Django-Ninja async views.
  ─ ZERO sync_to_async() usage.
  ─ All async selectors use Django 6.0 native async ORM:
      aget()                → single object lookup
      acount()              → COUNT aggregate
      aexists()             → EXISTS check
      aaggregate()          → SUM/COUNT/AVG aggregates
      afirst()              → first row or None
      [row async for qs]    → async QuerySet iteration
      aprefetch_related_objects([obj], ...) → async prefetch after aget()

Reverse FK / related-name traversal map for this domain:
  user.client_profile             → ClientProfile (OneToOne)
  user.user_orders                → Order rows for this client
  user.cart                       → Cart (OneToOne via get_or_create)
  profile.client_addresses               → ClientAddress rows (related_name="addresses")
  ProductWishlist.filter(user=)   → wishlist rows for this user

Google-style docstrings required for all non-trivial functions.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Count, QuerySet, Sum

from apps.client.models import ClientAddress, ClientProfile

logger = logging.getLogger(__name__)


def _address_filter_for_actor(actor) -> dict[str, Any] | None:
    """Return ClientAddress filter kwargs for either UnifiedUser or ClientProfile."""
    if actor is None:
        return None
    if actor.__class__.__name__ == "ClientProfile":
        return {"client": actor}
    return {"client__user": actor}


# ══════════════════════════════════════════════════════════════════════
#  SYNC selectors  (DRF views / admin / management commands)
# ══════════════════════════════════════════════════════════════════════


def get_client_profile_or_none(user) -> "QuerySet | None":  # noqa: F821
    """
    Return the ClientProfile for ``user`` with user pre-loaded, or None.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        ClientProfile instance or None if no profile exists.
    """
    try:
        return user.client_profile  # type: ignore[attr-defined]
    except Exception:
        return None


def get_client_addresses(user) -> "QuerySet":
    """
    Return all active (non-soft-deleted) addresses for ``user``.

    Ordered: default first, then most recently created.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        QuerySet[ClientAddress] ordered by -is_default, -created_at.
    """

    try:
        filter_kwargs = _address_filter_for_actor(user)
        if filter_kwargs is None:
            return []
        return ClientAddress.objects.filter(
            **filter_kwargs, is_deleted=False
        ).order_by("-is_default", "-created_at")
    except Exception:
        return []


def list_client_addresses(user) -> "QuerySet":
    """Alias for get_client_addresses (legacy compat)."""
    return get_client_addresses(user)


def get_client_stats(user) -> dict[str, Any]:
    """
    Return lightweight stats dict for the client.

    Used by JWT token serializer to embed quick data in login response.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        dict with total_orders, total_spent_ngn, is_profile_complete, preferred_size.
    """
    try:
        return ClientProfile.get_stats_for_user(user)
    except Exception:
        return {
            "total_orders": 0,
            "total_spent_ngn": 0,
            "is_profile_complete": False,
            "preferred_size": "",
        }


def get_client_address_list(user) -> list[dict]:
    """Return address rows as dictionaries for sync DRF/dashboard consumers."""
    return ClientProfile.get_address_list(user)


def get_client_order_stats(user) -> dict[str, Any]:
    """Return client order stats through the user.user_orders reverse relation."""
    return ClientProfile.get_order_stats_from_db(user)


def get_client_dashboard_snapshot(user) -> dict[str, Any]:
    """Return the sync client dashboard snapshot from model-level helpers."""
    return ClientProfile.get_full_dashboard_snapshot(user)


# ══════════════════════════════════════════════════════════════════════
#  ASYNC selectors  (Django-Ninja async router)
#  ── Only Django 6.0 native async ORM — ZERO sync_to_async ──
# ══════════════════════════════════════════════════════════════════════


async def aget_client_profile_or_none(user) -> "QuerySet | None":  # noqa: F821
    """
    Async: return the ClientProfile for ``user`` with user pre-loaded, or None.

    Uses aget() — the Django 6.0 async equivalent of .get().

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        ClientProfile instance or None.
    """
    try:
        return await ClientProfile.objects.select_related("user").aget(user=user)
    except ClientProfile.DoesNotExist:
        return None
    except Exception as exc:
        logger.error("aget_client_profile_or_none user=%s: %s", user, exc)
        return None


async def alist_client_addresses(user) -> list:
    """
    Async: return active addresses for a profile ordered with default first.

    Traversal: user.client_profile.client_addresses (related_name="addresses" on ClientAddress).
    Uses async iteration over the reverse FK queryset.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        list[ClientAddress] ordered by -is_default, -created_at.
    """
    filter_kwargs = _address_filter_for_actor(user)
    if filter_kwargs is None:
        return []
    return [
        address
        async for address in ClientAddress.objects.filter(
            **filter_kwargs,
            is_deleted=False,
        ).order_by(
            "-is_default",
            "-created_at",
        )
    ]


async def acount_client_addresses(user) -> int:
    """
    Async: return the number of active saved addresses for a profile.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        int — count of non-deleted addresses.
    """
    filter_kwargs = _address_filter_for_actor(user)
    if filter_kwargs is None:
        return 0
    return await ClientAddress.objects.filter(
        **filter_kwargs, is_deleted=False
    ).acount()


async def aget_client_addresses(user) -> list[dict]:
    """
    Async: return the shipping address list for a client user as list[dict].

    Traversal: user.client_profile.client_addresses (related_name="addresses").
    Uses async iteration over .values() — zero sync_to_async.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        list[dict] with id, label, recipient_name, address_line_1,
                   city, state, country, postal_code, phone, is_default, created_at.
    """

    try:
        filter_kwargs = _address_filter_for_actor(user)
        if filter_kwargs is None:
            return []
        qs = (
            ClientAddress.objects.filter(**filter_kwargs, is_deleted=False)
            .order_by("-is_default", "-created_at")
            .values(
                "id",
                "label",
                "full_name",
                "street_address",
                "city",
                "state",
                "country",
                "postal_code",
                "phone",
                "is_default",
                "created_at",
            )
        )
        return [row async for row in qs]
    except Exception as exc:
        logger.error("aget_client_addresses user=%s: %s", user, exc)
        return []


async def aget_client_address_list(user) -> list[dict]:
    """Compatibility alias for async address list reads."""
    return await ClientProfile.aget_address_list(user)


async def aget_client_order_summary(user) -> dict[str, Any]:
    """
    Async: return aggregated order statistics for a client user.

    Used in the client dashboard hero card (total orders, total spent,
    pending count, active count, completed count).

    Traversal: user.user_orders → Order rows → aaggregate() + acount().
    Uses aaggregate() for the SUM/COUNT in one query, then acount() for
    each status bucket as fast indexed queries.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        dict with total_orders, total_spent_ngn, pending_count,
               active_count, completed_count.
    """
    from apps.order.models import OrderStatus

    try:
        qs = user.user_orders.all()
        agg = await qs.aaggregate(
            total_orders=Count("id"),
            total_spent_ngn=Sum("total_amount"),
        )
        pending_count = await qs.filter(
            status=OrderStatus.PENDING_PAYMENT
        ).acount()
        active_count = await qs.filter(
            status__in=[
                OrderStatus.PAYMENT_CONFIRMED,
                OrderStatus.PROCESSING,
                OrderStatus.SHIPPED,
                OrderStatus.OUT_FOR_DELIVERY,
            ],
        ).acount()
        completed_count = await qs.filter(
            status__in=[OrderStatus.COMPLETED, OrderStatus.DELIVERED],
        ).acount()
        return {
            "total_orders": agg["total_orders"] or 0,
            "total_spent_ngn": float(agg["total_spent_ngn"] or 0),
            "pending_count": pending_count,
            "active_count": active_count,
            "completed_count": completed_count,
        }
    except Exception as exc:
        logger.error("aget_client_order_summary user=%s: %s", user, exc)
        return {
            "total_orders": 0,
            "total_spent_ngn": 0.0,
            "pending_count": 0,
            "active_count": 0,
            "completed_count": 0,
        }


async def aget_client_order_stats(user) -> dict[str, Any]:
    """Compatibility alias for async order stats reads."""
    return await ClientProfile.aget_order_stats_from_db(user)


async def aget_client_order_list(
    user,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """
    Async: return a paginated client order list as list[dict].

    Traversal: user.user_orders (related_name) → Order rows.
    Uses async iteration over .values() — zero sync_to_async.

    Args:
        user: Authenticated UnifiedUser instance.
        status: Optional OrderStatus string filter (e.g. "pending_payment").
        limit: Max rows to return (default 20).

    Returns:
        list[dict] with order_number, status, total_amount, currency,
                   created_at, vendor__store_name, fulfillment_type, paid_at.
    """

    try:
        qs = (
            user.user_orders.all()
            .select_related("vendor")
            .order_by("-created_at")
        )
        if status:
            qs = qs.filter(status=status)
        qs = qs.values(
            "id",
            "order_number",
            "status",
            "total_amount",
            "currency",
            "created_at",
            "fulfillment_type",
            "vendor__store_name",
            "paid_at",
            "tracking_number",
        )[:limit]
        return [row async for row in qs]
    except Exception as exc:
        logger.error("aget_client_order_list user=%s: %s", user, exc)
        return []


async def aget_client_wishlist(
    user,
    session_key: str | None = None,
) -> list[dict]:
    """
    Async: return wishlist items for a client user or anonymous session.

    Supports both authenticated users (user FK) and anonymous sessions
    (session_key) to satisfy the Anonymous Commerce Contract.

    Traversal (authenticated): user.product_wishlists (related_name)
    Traversal (anonymous):     ProductWishlist.filter(session_key=session_key)

    Uses async iteration over .values() — zero sync_to_async.

    Args:
        user: Authenticated user or None.
        session_key: Optional anonymous session key.

    Returns:
        list[dict] with wishlist_id, product_slug, product_title, price,
                   in_stock, stock_qty, created_at.
    """
    from apps.product.models import ProductWishlist

    try:
        if user is not None and getattr(user, "is_authenticated", False):
            base_filter = {"user": user}
        elif session_key:
            base_filter = {"user__isnull": True, "session_key": session_key}
        else:
            return []
        qs = (
            ProductWishlist.objects.filter(**base_filter)
            .select_related("product")
            .order_by("-created_at")
            .values(
                "id",
                "product__slug",
                "product__title",
                "product__price",
                "product__in_stock",
                "product__stock_qty",
                "created_at",
            )
        )
        return [row async for row in qs]
    except Exception as exc:
        logger.error(
            "aget_client_wishlist user=%s session=%s: %s", user, session_key, exc
        )
        return []


async def aget_client_measurement_summary(user) -> dict[str, Any]:
    """
    Async: return the latest active measurement snapshot for a client user.

    Traversal: user.client_profile.client_measurement_profiles.filter(is_active=True).latest().
    Uses afirst() — Django 6.0 async equivalent of .first().
    Returns empty dict if the user has no measurement profile.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        dict with measurement fields (height, weight, chest, waist, hip, etc.)
        or empty dict if no profile exists.
    """
    try:
        profile = await (
            user.client_profile.client_measurement_profiles.filter(is_active=True)
            .order_by("-created_at")
            .values(
                "id",
                "height_cm",
                "weight_kg",
                "chest_cm",
                "waist_cm",
                "hip_cm",
                "shoulder_cm",
                "arm_length_cm",
                "inseam_cm",
                "created_at",
                "updated_at",
            )
            .afirst()
        )
        return profile or {}
    except ImportError:
        # measurements app may not yet be migrated — graceful degradation
        return {}
    except Exception as exc:
        logger.error("aget_client_measurement_summary user=%s: %s", user, exc)
        return {}


async def aget_client_dashboard_snapshot(user) -> dict[str, Any]:
    """Return the full async dashboard snapshot from model-level helpers."""
    return await ClientProfile.aget_full_dashboard_snapshot(user)
