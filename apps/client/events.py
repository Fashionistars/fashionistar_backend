# apps/client/events.py
"""
Client Domain — EventBus Listener Registration.

Every event that the CLIENT domain cares about is wired here.
Listeners are registered once in ClientConfig.ready().

Events consumed:
  - user.registered  (role=client) → auto-create ClientProfile
  - user.verified                  → mark profile active / send welcome email
  - order.placed                   → increment client spend analytics (future)

Events emitted (by services, not here):
  - client.profile.updated
  - client.address.set_default
"""
import logging

from apps.common.events import EventBus

logger = logging.getLogger(__name__)


def _on_user_registered(payload: dict) -> None:
    """
    Auto-provision a blank ClientProfile when a new client registers.

    Called synchronously inside the same request/transaction.
    Runs idempotently — get_or_create is the safety net.
    """
    try:
        role = payload.get("role", "")
        if role != "client":
            return

        user_id = payload.get("user_id")
        if not user_id:
            logger.warning("client.events: user.registered missing user_id, skipping.")
            return

        # Import here to avoid circular during AppConfig.ready()
        from apps.authentication.models import UnifiedUser
        from apps.client.services.client_provisioning_service import ClientProvisioningService

        user = UnifiedUser.objects.get(pk=user_id)
        ClientProvisioningService.provision(user)

        logger.info("client.events: provisioned ClientProfile for user %s", user_id)

    except Exception:
        logger.exception("client.events: error in _on_user_registered handler")


def _on_user_verified(payload: dict) -> None:
    """
    When a client completes OTP/email verification, fire welcome email
    and mark the profile as active (is_profile_complete may be recalculated).
    """
    try:
        role = payload.get("role", "")
        if role != "client":
            return

        user_id = payload.get("user_id")
        if not user_id:
            return

        from apps.client.tasks import send_client_welcome_email
        send_client_welcome_email.apply_async(
            kwargs={"user_id": str(user_id)},
            retry=False,
            ignore_result=True,
        )
        logger.info("client.events: queued welcome email for user %s", user_id)

    except Exception:
        logger.exception("client.events: error in _on_user_verified handler")


def register_listeners() -> None:
    """
    Register all client domain EventBus listeners.
    Called exactly once in ClientConfig.ready().
    """
    EventBus.on("user.registered", _on_user_registered)
    EventBus.on("user.verified", _on_user_verified)
    logger.debug("client.events: EventBus listeners registered.")
