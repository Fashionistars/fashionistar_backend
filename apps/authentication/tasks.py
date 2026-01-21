# apps/authentication/tasks.py

from celery import shared_task
import logging
from django.conf import settings
from django.template.exceptions import TemplateDoesNotExist
from utilities.managers.email import EmailManager
from utilities.managers.sms import SMSManager

# Get logger for application
application_logger = logging.getLogger('application')

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
        application_logger.info(f"📧 Sending email to {recipients} using template {template_name}")
        EmailManager.send_mail(
            subject=subject,
            recipients=recipients,
            template_name=template_name,
            context=context,
            attachments=attachments,
        )
        application_logger.info(f"✅ Email sent successfully to {recipients}")
        return f"Email sent successfully to {recipients}"

    except TemplateDoesNotExist as e:
        application_logger.error(f"🚨 Template missing / not found: {template_name} - {e}", exc_info=True)
        raise  # Re-raise to prevent retry for missing templates

    except Exception as exc:
        application_logger.exception(f"❌ Error sending email to {recipients}, retrying... Error: {exc}")
        # Retry the task with exponential backoff.
        raise self.retry(exc=exc, countdown=60)


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
        message_sid = SMSManager.send_sms(to=to, body=body)
        application_logger.info(f"SMS sent successfully to {to} with SID: {message_sid}")
        return message_sid
    except Exception as exc:
        application_logger.error(f"Error sending SMS to {to}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)
