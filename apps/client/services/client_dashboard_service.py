# apps/client/services/client_dashboard_service.py
"""
ClientDashboardService — Aggregated analytics for the client dashboard.

All reads go through optimized ORM queries (select_related + values()).
No raw SQL. Designed for the async Ninja dashboard endpoint.
"""
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

        Returns a dict with:
          - profile completeness
          - total_orders, total_spent_ngn
          - recent activity snapshot
          - ai_recommendations stub (future)
        """
        try:
            from apps.client.models import ClientProfile, ClientAddress

            # Async ORM fetch
            profile = await ClientProfile.objects.select_related("user").aget(user=user)
            address_count = await ClientAddress.objects.filter(
                client=profile, is_deleted=False
            ).acount()

            return {
                "profile": {
                    "id": str(profile.pk),
                    "bio": profile.bio,
                    "preferred_size": profile.preferred_size,
                    "style_preferences": profile.style_preferences,
                    "favourite_colours": profile.favourite_colours,
                    "country": profile.country,
                    "is_profile_complete": profile.is_profile_complete,
                },
                "analytics": {
                    "total_orders": profile.total_orders,
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
