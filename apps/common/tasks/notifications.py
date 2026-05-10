# apps/common/tasks/notifications.py
"""
User notification Celery tasks.

Tasks:
    send_account_status_email  — Email user on account soft/hard-delete or restore.
    send_account_status_sms    — SMS user on account soft/hard-delete or restore.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


# ================================================================
# ACCOUNT STATUS — EMAIL
# ================================================================

@shared_task(
    name="send_account_status_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_account_status_email(self, email, action, context=None):
    """
    Send an email notification when a user's account status
    changes (soft-deleted, hard-deleted, restored).

    Args:
        email (str): Recipient email address.
        action (str): One of 'soft_deleted', 'hard_deleted', 'restored'.
        context (dict, optional): Extra template context.
    """
    from apps.common.managers.email import EmailManager

    if not email:
        logger.warning(
            "send_account_status_email called with no email for action=%s", action
        )
        return

    subjects = {
        "soft_deleted": "Your account has been deactivated",
        "hard_deleted": "Your account has been permanently deleted",
        "restored":     "Your account has been restored",
    }
    messages = {
        "soft_deleted": (
            "Your account has been deactivated by an administrator. "
            "If you believe this is a mistake, please contact our support team."
        ),
        "hard_deleted": (
            "Your account has been permanently removed from our platform. "
            "All associated data has been deleted. "
            "If you have questions, please contact our support team."
        ),
        "restored": (
            "Your account has been successfully restored. "
            "You can now log in and use all platform features as before."
        ),
    }

    subject = subjects.get(action, "Account status update")
    body    = messages.get(action, "Your account status has changed.")

    try:
        EmailManager.send_mail(
            subject=subject,
            recipients=[email],
            message=body,
            fail_silently=False,
        )
        logger.info("Account status email [%s] sent to %s", action, email)
    except Exception as exc:
        logger.exception(
            "Failed to send account status email [%s] to %s", action, email
        )
        raise self.retry(exc=exc)


# ================================================================
# ACCOUNT STATUS — SMS
# ================================================================

@shared_task(
    name="send_account_status_sms",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_account_status_sms(self, phone, action, context=None):
    """
    Send an SMS notification when a user's account status changes.

    Args:
        phone (str): Recipient phone number (E.164 format).
        action (str): One of 'soft_deleted', 'hard_deleted', 'restored'.
        context (dict, optional): Reserved for future template support.
    """
    from apps.common.managers.sms import SMSManager

    if not phone:
        logger.warning(
            "send_account_status_sms called with no phone for action=%s", action
        )
        return

    messages = {
        "soft_deleted": (
            "Your account has been deactivated. "
            "Contact support if this is a mistake."
        ),
        "hard_deleted": (
            "Your account has been permanently deleted. "
            "Contact support for questions."
        ),
        "restored": (
            "Your account has been restored. You can now log in again."
        ),
    }

    body = messages.get(action, "Your account status has changed.")

    try:
        SMSManager.send_sms(to=str(phone), body=body)
        logger.info("Account status SMS [%s] sent to %s", action, phone)
    except Exception as exc:
        logger.exception(
            "Failed to send account status SMS [%s] to %s", action, phone
        )
        raise self.retry(exc=exc)
