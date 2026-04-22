# apps/vendor/events.py
"""
Vendor Domain — EventBus Listener Registration.

Events consumed:
  - user.registered (role=vendor) → auto-provision VendorProfile + SetupState
  - user.verified   (role=vendor) → unlock/notify onboarding start

Events emitted (by services):
  - vendor.profile.updated
  - vendor.setup.step_completed
  - vendor.onboarding.done
"""
import logging

from apps.common.events import EventBus

logger = logging.getLogger(__name__)


def _on_user_registered(payload: dict) -> None:
    """
    Auto-provision a VendorProfile + VendorSetupState when a vendor registers.
    """
    try:
        if payload.get("role") != "vendor":
            return

        user_id = payload.get("user_id")
        if not user_id:
            logger.warning("vendor.events: user.registered missing user_id — skipping.")
            return

        from apps.authentication.models import UnifiedUser
        from apps.vendor.services.vendor_provisioning_service import VendorProvisioningService

        user = UnifiedUser.objects.get(pk=user_id)
        VendorProvisioningService.provision(user)
        logger.info("vendor.events: provisioned VendorProfile for user %s", user_id)

    except Exception:
        logger.exception("vendor.events: error in _on_user_registered")


def _on_user_verified(payload: dict) -> None:
    """
    When a vendor completes verification, send onboarding start email.
    """
    try:
        if payload.get("role") != "vendor":
            return

        user_id = payload.get("user_id")
        if not user_id:
            return

        from apps.vendor.tasks import send_vendor_onboarding_email
        send_vendor_onboarding_email.apply_async(
            kwargs={"user_id": str(user_id)},
            retry=False,
            ignore_result=True,
        )
        logger.info("vendor.events: queued onboarding email for user %s", user_id)

    except Exception:
        logger.exception("vendor.events: error in _on_user_verified")


def register_listeners() -> None:
    """Register all vendor domain EventBus listeners. Called once in VendorConfig.ready()."""
    EventBus.on("user.registered", _on_user_registered)
    EventBus.on("user.verified",   _on_user_verified)
    logger.debug("vendor.events: EventBus listeners registered.")
