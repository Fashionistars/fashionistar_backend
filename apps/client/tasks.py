# apps/client/tasks.py
"""
Client Domain — Celery Tasks.

All tasks are fire-and-forget: retry=False, ignore_result=True.
They NEVER block the main request thread.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="client.provision_defaults",
    bind=True,
    max_retries=0,
    ignore_result=True,
    soft_time_limit=30,
    time_limit=60,
)
def provision_client_defaults(self, user_id: str) -> None:
    """
    Idempotently create the default client-domain records for a new user.

    This is intentionally asynchronous so registration/login never waits
    on client profile provisioning.
    """
    try:
        from apps.authentication.models import UnifiedUser
        from apps.client.services.client_provisioning_service import (
            ClientProvisioningService,
        )

        user = UnifiedUser.objects.get(pk=user_id)
        if getattr(user, "role", None) != "client":
            logger.warning(
                "client.provision_defaults: user %s is not a client, skipping.",
                user_id,
            )
            return

        ClientProvisioningService.provision(user)
        logger.info(
            "client.provision_defaults: ensured client defaults for user %s",
            user_id,
        )
    except Exception:
        logger.exception(
            "client.provision_defaults: error while provisioning user_id=%s",
            user_id,
        )


@shared_task(
    name="client.send_welcome_email",
    bind=True,
    max_retries=0,
    ignore_result=True,
    soft_time_limit=30,
    time_limit=60,
)
def send_client_welcome_email(self, user_id: str) -> None:
    """
    Send a welcome email to a newly verified client.

    Args:
        user_id: UUID string of the UnifiedUser.
    """
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        from apps.authentication.models import UnifiedUser

        user = UnifiedUser.objects.get(pk=user_id)
        recipient = getattr(user, "email", None)
        if not recipient:
            logger.warning(
                "client.send_welcome_email: user %s has no email, skipping.", user_id
            )
            return

        send_mail(
            subject="Welcome to Fashionistar! 🎉",
            message=(
                f"Hi {getattr(user, 'full_name', 'there')},\n\n"
                "Your account is verified and ready.\n"
                "Start exploring Nigeria's #1 AI Fashion Marketplace.\n\n"
                "— The Fashionistar Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=True,
        )
        logger.info("client.send_welcome_email: sent to %s", recipient)

    except Exception:
        logger.exception(
            "client.send_welcome_email: error for user_id=%s", user_id
        )


@shared_task(
    name="client.recalculate_completeness",
    bind=True,
    max_retries=2,
    ignore_result=True,
    soft_time_limit=30,
    time_limit=60,
)
def recalculate_client_profile_completeness(self, profile_id: str) -> None:
    """
    Recalculate and persist is_profile_complete for a ClientProfile.
    Triggered after profile updates.
    """
    try:
        from apps.client.models import ClientProfile
        profile = ClientProfile.objects.get(pk=profile_id)
        profile.update_completeness()
        logger.info(
            "client.recalculate_completeness: profile %s complete=%s",
            profile_id, profile.is_profile_complete,
        )
    except Exception:
        logger.exception(
            "client.recalculate_completeness: error for profile_id=%s", profile_id
        )
