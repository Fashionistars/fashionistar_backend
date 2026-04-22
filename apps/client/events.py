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

logger = logging.getLogger(__name__)


def _on_user_registered(
    user_uuid: str,
    role: str = "",
    **_,
) -> None:
    """
    Queue async default provisioning for a newly registered client.

    The EventBus fires after ``transaction.on_commit()``, so the user row
    already exists. The actual profile creation runs in Celery so dashboard
    access is never blocked by client-domain default provisioning.
    """
    try:
        if role != "client":
            return

        if not user_uuid:
            logger.warning("client.events: user.registered missing user_uuid, skipping.")
            return

        from apps.client.tasks import provision_client_defaults
        provision_client_defaults.apply_async(
            kwargs={"user_id": str(user_uuid)},
            retry=False,
            ignore_result=True,
        )
        logger.info(
            "client.events: queued async client provisioning for user %s",
            user_uuid,
        )

    except Exception:
        logger.exception("client.events: error in _on_user_registered handler")


def _on_user_verified(
    user_uuid: str,
    role: str = "",
    **_,
) -> None:
    """
    When a client completes OTP/email verification, fire welcome email
    and mark the profile as active (is_profile_complete may be recalculated).
    """
    try:
        if role != "client":
            return

        if not user_uuid:
            return

        from apps.client.tasks import send_client_welcome_email
        send_client_welcome_email.apply_async(
            kwargs={"user_id": str(user_uuid)},
            retry=False,
            ignore_result=True,
        )
        logger.info("client.events: queued welcome email for user %s", user_uuid)

    except Exception:
        logger.exception("client.events: error in _on_user_verified handler")


def register_listeners() -> None:
    """
    Register all client domain EventBus listeners.
    Called exactly once in ClientConfig.ready().
    """
    from apps.common.events import event_bus

    event_bus.subscribe("user.registered", _on_user_registered)
    event_bus.subscribe("user.verified", _on_user_verified)
    logger.debug("client.events: EventBus listeners registered.")
