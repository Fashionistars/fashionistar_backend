# apps/client/services/client_dashboard_service.py
"""
ClientDashboardService — Aggregated analytics for the client dashboard.

All reads go through the selectors layer. Independent lookups are gathered
concurrently so Ninja dashboard reads stay aligned with the read-async,
write-sync architecture.
"""
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ClientDashboardService:
    """
    Aggregates all metrics needed to render the client dashboard.
    """

    @classmethod
    async def get_dashboard_summary(cls, user) -> dict[str, Any]:
        """
        Build the complete dashboard payload for `user`.
        Returns a dict fully compatible with DashboardOut → ProfileOut so
        Pydantic validation never fails on required fields.

        Returns a dict with:
          - profile completeness
          - total_orders, total_spent_ngn
          - recent activity snapshot
          - ai_recommendations stub (future)
        """
        try:
            from apps.client.selectors.client_selectors import (
                acount_client_addresses,
                aget_client_profile_or_none,
            )
            from apps.client.services.client_provisioning_service import (
                ClientProvisioningService,
            )

            profile = await aget_client_profile_or_none(user)
            if profile is None:
                profile = await ClientProvisioningService.aprovision(user)

            address_count, = await asyncio.gather(
                acount_client_addresses(profile),
            )

            return {
                "profile": {
                    # ── Primary key ──────────────────────────────────────────
                    "id": str(profile.pk),

                    # ── User identity (required by ProfileOut) ───────────────
                    "user_id":    str(user.pk),
                    "user_email": getattr(user, "email", "") or "",

                    # ── Profile text fields ──────────────────────────────────
                    "bio":                      profile.bio or "",
                    "default_shipping_address": profile.default_shipping_address or "",
                    "preferred_size":           profile.preferred_size or "",
                    "style_preferences":        profile.style_preferences or [],
                    "favourite_colours":        profile.favourite_colours or [],
                    "country":                  profile.country or "",
                    "state":                    profile.state or "",
                    "is_profile_complete":      profile.is_profile_complete,

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
                    "total_orders":    profile.total_orders,
                    "total_spent_ngn": float(profile.total_spent_ngn),
                    "saved_addresses": address_count,
                },
                "ai_recommendations": [],  # Populated by AI service in future sprint
            }
        except Exception:
            logger.exception(
                "ClientDashboardService.get_dashboard_summary: error for user %s",
                getattr(user, "pk", "?"),
            )
            raise
