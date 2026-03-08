# apps/authentication/tasks.py
"""
Celery Tasks for Authentication Module.

These tasks offload I/O-heavy operations (email, SMS) to background workers,
preventing request/response cycles from blocking on SMTP or HTTP calls.

Architecture:
    - send_email_task: Dispatches templated emails via EmailManager.
    - send_sms_task: Dispatches SMS messages via SMSManager.

Both tasks use exponential backoff with max 3 retries.
"""

from celery import shared_task
import logging
from django.conf import settings
from django.template.exceptions import TemplateDoesNotExist

# ── Corrected import paths (apps.common, not utilities) ─────────────
from apps.common.managers.email import EmailManager, EmailManagerError
from apps.common.managers.sms import SMSManager

# Per-module logger — auto-routes to logs/apps/authentication/auth.log
logger = logging.getLogger(__name__)

@shared_task(bind=True, retry_backoff=True, max_retries=3)
def send_email_task(self, subject: str, recipients: list[str], template_name: str, context: dict, attachments: list[tuple] | None = None) -> str:
    """
    Sends an email asynchronously using Celery, leveraging the EmailManager.
    Handles potential template errors and retries.

    Args:
        self (celery.Task): The Celery task instance.
        subject (str): Email subject.
        recipients (list[str]): List of recipient email addresses.
        template_name (str): Path to the HTML email template.
        context (dict): Dictionary of data to pass to the template.
        attachments (list[tuple] | None): Optional list of attachments (filename, content, mimetype).

    Returns:
        str: A success message, or raises an exception on failure.

    Raises:
        TemplateDoesNotExist: If the specified template does not exist. The task will NOT be retried.
        Exception: If an error occurs during email sending, the task will be retried with exponential backoff.
    """
    try:
        logger.info("📧 [Celery] Sending email → recipients=%s template=%s",
                    recipients, template_name)
        EmailManager.send_mail(
            subject=subject,
            recipients=recipients,
            template_name=template_name,
            context=context,
            attachments=attachments,
        )
        logger.info("✅ [Celery] Email sent → %s", recipients)
        return f"Email sent successfully to {recipients}"

    except (TemplateDoesNotExist, EmailManagerError) as exc:
        # Template missing or invalid args — retrying won't help.
        # EmailManagerError wraps TemplateDoesNotExist inside EmailManager.
        logger.error("🚨 [Celery] Template/config error: %s — %s",
                     template_name, exc, exc_info=True)
        raise  # Fail the task permanently — no retry

    except Exception as exc:
        logger.warning(
            "⚠️ [Celery] Email send failed (attempt %s/%s) → %s: %s",
            self.request.retries + 1, self.max_retries + 1, recipients, exc
        )
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@shared_task(bind=True, retry_backoff=True, max_retries=3)
def send_sms_task(self, to: str, body: str) -> str:
    """
    Sends an SMS asynchronously using Celery, leveraging the SMSManager.

    Args:
        self (celery.Task): The Celery task instance.
        to (str): Recipient's phone number (in E.164 format).
        body (str): SMS message body.

    Returns:
        str: Message SID or Success Message.

    Raises:
        Exception: If an error occurs during SMS sending, the task will be retried with exponential backoff.
    """
    try:
        logger.info("📱 [Celery] Sending SMS → to=%s", to)
        message_sid = SMSManager.send_sms(to=to, body=body)
        logger.info("✅ [Celery] SMS sent → %s (SID: %s)", to, message_sid)
        return message_sid
    except Exception as exc:
        logger.warning(
            "⚠️ [Celery] SMS send failed (attempt %s/%s) → %s: %s",
            self.request.retries + 1, self.max_retries + 1, to, exc
        )
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
