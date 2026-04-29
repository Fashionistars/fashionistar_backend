# apps/vendor/events.py
"""
Vendor Domain — EventBus Listener Registration.

Events consumed:
  - user.verified   (role=vendor) → send onboarding/start-setup email

Events emitted (by services):
  - vendor.profile.updated
  - vendor.setup.step_completed
  - vendor.onboarding.done
"""
import logging

from apps.common.roles import is_vendor_role

logger = logging.getLogger(__name__)


def _on_user_verified(
    user_uuid: str,
    role: str = "",
    **_,
) -> None:
    """
    When a vendor completes verification, send setup/onboarding guidance.
    """
    try:
        if not is_vendor_role(role):
            return

        if not user_uuid:
            return

        from apps.vendor.tasks import send_vendor_onboarding_email
        send_vendor_onboarding_email.apply_async(
            kwargs={"user_id": str(user_uuid)},
            retry=False,
            ignore_result=True,
        )
        logger.info("vendor.events: queued onboarding email for user %s", user_uuid)

    except Exception:
        logger.exception("vendor.events: error in _on_user_verified")


def register_listeners() -> None:
    """Register all vendor domain EventBus listeners. Called once in VendorConfig.ready()."""
    from apps.common.events import event_bus

    event_bus.subscribe("user.verified", _on_user_verified)
    logger.debug("vendor.events: EventBus listeners registered.")
