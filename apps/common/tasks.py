# apps/common/tasks.py
"""
Celery background tasks for ``apps.common``.

All heavy I/O operations (email, SMS, HTTP pings) are offloaded
here so that request/response cycles and admin actions remain
fast and non-blocking.

Tasks:
    - keep_service_awake: Periodic health ping for Render free-tier.
    - send_account_status_email: Notify user of account status changes.
    - send_account_status_sms: Notify user of account status changes.
"""

import logging

import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger('application')


# ================================================================
# 1. SERVICE HEALTH PING
# ================================================================

@shared_task(
    name="keep_service_awake",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def keep_service_awake(self):
    """
    Periodic task that pings the application URL to prevent
    Render free-tier spin-down.

    Retries up to 2 times on failure with a 30-second delay.
    """
    site_url = getattr(settings, 'SITE_URL', None)

    if not site_url:
        logger.warning(
            "SITE_URL is not configured. "
            "Cannot run keep_service_awake task."
        )
        return

    try:
        response = requests.get(site_url, timeout=15)
        if response.status_code == 200:
            logger.info(
                "Successfully pinged %s to keep service awake",
                site_url,
            )
        else:
            logger.error(
                "Failed to ping %s. Status: %s",
                site_url,
                response.status_code,
            )
    except requests.exceptions.RequestException as exc:
        logger.error(
            "Error pinging %s: %s",
            site_url,
            exc,
        )
        raise self.retry(exc=exc)


# ================================================================
# 2. ACCOUNT STATUS NOTIFICATIONS (Soft/Hard Delete & Restore)
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

    Dispatched as a Celery background task to avoid blocking
    admin actions or model save operations.

    Args:
        email (str): Recipient email address.
        action (str): One of 'soft_deleted', 'hard_deleted',
            'restored'.
        context (dict, optional): Extra template context
            (e.g., user name, support URL).
    """
    from apps.common.managers.email import EmailManager

    if not email:
        logger.warning(
            "send_account_status_email called with no email "
            "for action=%s",
            action,
        )
        return

    subjects = {
        'soft_deleted': "Your account has been deactivated",
        'hard_deleted': "Your account has been permanently deleted",
        'restored': "Your account has been restored",
    }
    messages = {
        'soft_deleted': (
            "Your account has been deactivated by an "
            "administrator. If you believe this is a mistake, "
            "please contact our support team."
        ),
        'hard_deleted': (
            "Your account has been permanently removed from "
            "our platform. All associated data has been "
            "deleted. If you have questions, please contact "
            "our support team."
        ),
        'restored': (
            "Your account has been successfully restored. "
            "You can now log in and use all platform features "
            "as before."
        ),
    }

    subject = subjects.get(action, "Account status update")
    body = messages.get(action, "Your account status has changed.")

    try:
        EmailManager.send_mail(
            subject=subject,
            recipients=[email],
            message=body,
            fail_silently=False,
        )
        logger.info(
            "Account status email [%s] sent to %s",
            action,
            email,
        )
    except Exception as exc:
        logger.exception(
            "Failed to send account status email [%s] to %s",
            action,
            email,
        )
        raise self.retry(exc=exc)


@shared_task(
    name="send_account_status_sms",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_account_status_sms(self, phone, action, context=None):
    """
    Send an SMS notification when a user's account status
    changes (soft-deleted, hard-deleted, restored).

    Dispatched as a Celery background task to avoid blocking
    admin actions or model save operations.

    Args:
        phone (str): Recipient phone number (E.164 format).
        action (str): One of 'soft_deleted', 'hard_deleted',
            'restored'.
        context (dict, optional): Extra context (unused for
            SMS, reserved for future template support).
    """
    from apps.common.managers.sms import SMSManager

    if not phone:
        logger.warning(
            "send_account_status_sms called with no phone "
            "for action=%s",
            action,
        )
        return

    messages = {
        'soft_deleted': (
            "Your account has been deactivated. "
            "Contact support if this is a mistake."
        ),
        'hard_deleted': (
            "Your account has been permanently deleted. "
            "Contact support for questions."
        ),
        'restored': (
            "Your account has been restored. "
            "You can now log in again."
        ),
    }

    body = messages.get(action, "Your account status has changed.")

    try:
        SMSManager.send_sms(to=str(phone), body=body)
        logger.info(
            "Account status SMS [%s] sent to %s",
            action,
            phone,
        )
    except Exception as exc:
        logger.exception(
            "Failed to send account status SMS [%s] to %s",
            action,
            phone,
        )
        raise self.retry(exc=exc)