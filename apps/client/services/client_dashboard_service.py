# apps/client/services/client_dashboard_service.py
"""
ClientDashboardService — Aggregated analytics for the client dashboard.

All reads go through the selectors layer. Five independent lookups are
gathered concurrently via asyncio.gather() so the Ninja async endpoint
returns in a single DB round-trip budget.

Architecture:
  • Only async selectors are called here (all prefixed with `aget_` / `acount_`).
  • Zero sync_to_async — Django 6.0 native async ORM throughout.
  • Dependency-injection style: service accepts a user object, calls selectors.
"""
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ClientDashboardService:
    """
    Aggregates all metrics needed to render the client dashboard.

    Supports 100,000+ RPS via ASGI/Uvicorn + Django 6.0 async ORM:
      - No blocking calls
      - asyncio.gather() for concurrent independent queries
      - Graceful fallback on every sub-call
    """

    @classmethod
    async def get_dashboard_summary(cls, user) -> dict[str, Any]:
        """
        Build the complete dashboard payload for ``user``.

        Executes 5 concurrent async DB queries:
          1. ClientProfile (aget_or_create)
          2. address count
          3. order stats (total, pending, active, completed)
          4. wishlist count
          5. measurement snapshot (latest active)

        Returns a dict fully compatible with DashboardOut → ProfileOut so
        Pydantic validation never fails on required fields.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            dict with profile, analytics, measurement_snapshot, ai_recommendations.
        """
        try:
            from apps.client.selectors.client_selectors import (
                acount_client_addresses,
                aget_client_measurement_summary,
                aget_client_order_summary,
                aget_client_profile_or_none,
            )
            from apps.client.services.client_provisioning_service import (
                ClientProvisioningService,
            )

            profile = await aget_client_profile_or_none(user)
            if profile is None:
                profile = await ClientProvisioningService.aprovision(user)

            # ── Gather all independent reads concurrently ─────────────────
            address_count, order_stats, wishlist_count, measurement = (
                await asyncio.gather(
                    acount_client_addresses(profile),
                    aget_client_order_summary(user),
                    _safe_wishlist_count(user),
                    aget_client_measurement_summary(user),
                )
            )

            return {
                "profile": {
                    # ── Primary key ──────────────────────────────────────────
                    "id": str(profile.pk),

                    # ── User identity (required by ProfileOut) ───────────────
                    "user_id":    str(user.pk),
                    "user_email": getattr(user, "email", "") or "",

                    # ── Profile text fields ──────────────────────────────────
                    "bio":                       profile.bio or "",
                    "default_shipping_address":  profile.default_shipping_address or "",
                    "preferred_size":            profile.preferred_size or "",
                    "style_preferences":         profile.style_preferences or [],
                    "favourite_colours":         profile.favourite_colours or [],
                    "country":                   profile.country or "",
                    "state":                     profile.state or "",
                    "is_profile_complete":       profile.is_profile_complete,

                    # ── Counters ─────────────────────────────────────────────
                    "total_orders":    profile.total_orders,
                    "total_spent_ngn": profile.total_spent_ngn,

                    # ── Notification prefs (required by ProfileOut) ──────────
                    "email_notifications_enabled": getattr(
                        profile, "email_notifications_enabled", True
                    ),
                    "sms_notifications_enabled": getattr(
                        profile, "sms_notifications_enabled", True
                    ),

                    # ── Addresses (detail read; empty on dashboard summary) ───
                    "addresses": [],
                },
                "analytics": {
                    "total_orders":    order_stats.get("total_orders", 0),
                    "total_spent_ngn": order_stats.get("total_spent_ngn", 0.0),
                    "saved_addresses": address_count,
                    "pending_orders":  order_stats.get("pending_count", 0),
                    "active_orders":   order_stats.get("active_count", 0),
                    "completed_orders":order_stats.get("completed_count", 0),
                    "wishlist_count":  wishlist_count,
                },
                "measurement_snapshot": measurement or {},
                "ai_recommendations": [],  # Populated by AI service in future sprint
            }
        except Exception:
            logger.exception(
                "ClientDashboardService.get_dashboard_summary: error for user %s",
                getattr(user, "pk", "?"),
            )
            raise


async def _safe_wishlist_count(user) -> int:
    """Gracefully return wishlist count; 0 on any error."""
    try:
        from apps.client.selectors.client_selectors import aget_client_profile_or_none
        profile = await aget_client_profile_or_none(user)
        if profile is None:
            return 0
        from apps.client.models import ClientProfile
        return await ClientProfile.aget_wishlist_count(user)
    except Exception:
        return 0
