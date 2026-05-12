# apps/vendor/tasks.py
"""Vendor Domain — Celery Tasks (fire-and-forget)."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="vendor.send_onboarding_email",
    bind=True, max_retries=0, ignore_result=True,
    soft_time_limit=30, time_limit=60,
)
def send_vendor_onboarding_email(self, user_id: str) -> None:
    """Send onboarding instructions to a newly verified vendor."""
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        from apps.authentication.models import UnifiedUser

        user = UnifiedUser.objects.get(pk=user_id)
        recipient = getattr(user, "email", None)
        if not recipient:
            return

        send_mail(
            subject="Welcome to Fashionistar Vendors! Set up your store 🎉",
            message=(
                f"Hi {getattr(user, 'full_name', 'there')},\n\n"
                "Your vendor account is verified.\n"
                "Complete your store setup at:\n"
                "https://fashionistar.net/vendor/setup\n\n"
                "— The Fashionistar Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=True,
        )
        logger.info("vendor.send_onboarding_email: sent to %s", recipient)
    except Exception:
        logger.exception("vendor.send_onboarding_email: error for user_id=%s", user_id)
