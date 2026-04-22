# apps/vendor/services/vendor_dashboard_service.py
"""
VendorDashboardService — Async aggregated analytics for vendor dashboard.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class VendorDashboardService:
    """
    Aggregates all metrics needed to render the vendor dashboard.
    All methods are async — used by the Ninja async router.
    """

    @classmethod
    async def get_dashboard_summary(cls, user) -> dict[str, Any]:
        """
        Build the complete vendor dashboard payload.

        Returns:
          - profile (store info, verification status)
          - setup_state (onboarding progress)
          - analytics (products, sales, revenue, rating)
          - recent_activity (stub for future sprint)
        """
        try:
            from apps.vendor.models import VendorProfile, VendorSetupState

            profile = await VendorProfile.objects.select_related("user").aget(user=user)

            # Setup state (may not exist for very old vendors pre-migration)
            try:
                setup = await VendorSetupState.objects.aget(vendor=profile)
                setup_data = {
                    "current_step": setup.current_step,
                    "profile_complete": setup.profile_complete,
                    "bank_details": setup.bank_details,
                    "id_verified": setup.id_verified,
                    "first_product": setup.first_product,
                    "onboarding_done": setup.onboarding_done,
                    "completion_percentage": setup.completion_percentage,
                }
            except VendorSetupState.DoesNotExist:
                setup_data = {
                    "current_step": 1,
                    "profile_complete": False,
                    "bank_details": False,
                    "id_verified": False,
                    "first_product": False,
                    "onboarding_done": False,
                    "completion_percentage": 0,
                }

            return {
                "profile": {
                    "id": str(profile.pk),
                    "store_name": profile.store_name,
                    "store_slug": profile.store_slug,
                    "tagline": profile.tagline,
                    "logo_url": profile.logo_url,
                    "cover_url": profile.cover_url,
                    "city": profile.city,
                    "state": profile.state,
                    "country": profile.country,
                    "is_verified": profile.is_verified,
                    "is_active": profile.is_active,
                    "is_featured": profile.is_featured,
                },
                "analytics": {
                    "total_products": profile.total_products,
                    "total_sales": profile.total_sales,
                    "total_revenue": float(profile.total_revenue),
                    "average_rating": float(profile.average_rating),
                    "review_count": profile.review_count,
                },
                "setup_state": setup_data,
                "recent_activity": [],  # Populated by activity service in future sprint
            }

        except Exception:
            logger.exception(
                "VendorDashboardService.get_dashboard_summary: error for user %s",
                getattr(user, "pk", "?"),
            )
            raise
