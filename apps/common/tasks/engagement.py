"""
Public engagement Celery tasks.

Handles lightweight unauthenticated lead-capture notifications for the
public commerce funnel:
  - contact form submissions
  - newsletter signups
  - waitlist joins
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="send_public_engagement_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_public_engagement_email(
    self,
    *,
    subject: str,
    recipients: list[str],
    message: str,
) -> str:
    """Send a plain-text engagement email to the configured support inbox."""
    from apps.common.managers.email import EmailManager

    if not recipients:
        logger.warning("send_public_engagement_email called without recipients")
        return "no_recipients"

    try:
        EmailManager.send_mail(
            subject=subject,
            recipients=recipients,
            message=message,
            fail_silently=False,
        )
        logger.info(
            "Public engagement email sent: subject=%s recipients=%s",
            subject,
            recipients,
        )
        return "sent"
    except Exception as exc:
        logger.exception(
            "Failed to send public engagement email: subject=%s recipients=%s",
            subject,
            recipients,
        )
        raise self.retry(exc=exc)
