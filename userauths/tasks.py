# userauths/celery_task.py

from celery import shared_task
import logging
from django.conf import settings
from userauths.UTILS.email_utils import EmailManager  # Import your EmailManager
from django.template.exceptions import TemplateDoesNotExist

application_logger = logging.getLogger('application')


from django.conf import settings
from twilio.rest import Client  # Import the Twilio Client



@shared_task(bind=True, retry_backoff=True, max_retries=3)
def send_email_task(self, subject: str, recipients: list[str], template_name: str, context: dict, attachments: list[tuple] | None = None) -> str:
    """
    Sends an email asynchronously using Celery, leveraging the EmailManager.
    Handles potential template errors and retries.

    Args:
        subject: Email subject.
        recipients: List of recipient email addresses.
        template_name: Path to the HTML email template.
        context: Dictionary of data to pass to the template.
        attachments: Optional list of attachments (filename, content, mimetype).

    Returns:
        A success message, or raises an exception on failure.
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
        raise  # Re-raise the exception to prevent retry, as the template issue won't resolve itself.  Fix template error!

    except Exception as exc:
        application_logger.exception(f"❌ Error sending email to {recipients}, retrying... Error: {exc}")  # Use exception for full traceback
        # Retry the task with exponential backoff.
        raise self.retry(exc=exc, countdown=60)












# from celery import shared_task
# from django.conf import settings
# import logging
# # from .utils import EmailManager, SMSManager
# from userauths.UTILS.email_utils import EmailManager
# import time
# from django.utils import timezone

# application_logger = logging.getLogger('application')


# @shared_task(bind=True, retry_backoff=True, max_retries=3)
# def process_email_queue_task(self):
#     """Process the email queue."""
#     try:
#         EmailManager.process_email_queue()  # Invoke the email processing method
#         application_logger.info(f"Email Queue Processed {timezone.now()}")
#         return f"Email Queue Processed Successfully {timezone.now()}"
#     except Exception as exc:
#         application_logger.error(f"Error when processing Email Queue {exc}", exc_info=True)
#         raise self.retry(exc=exc, countdown=60) # Retry exponential backoff
























class SMSManagerError(Exception):
    """Raise an exception if an error occurs in the SMS manager"""

class SMSManager:
    """
    Manages the sending of SMS messages using Twilio.
    """

    @classmethod
    def send_sms(cls, to: str, body: str) -> str:
        """
        Sends an SMS using Twilio.

        Args:
            to (str): Recipient's phone number (in E.164 format).
            body (str): SMS message body.

        Returns:
            str: Message SID (string).

        Raises:
            SMSManagerError: If an error occurs during SMS sending.
        """
        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=body,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=to
            )
            application_logger.info(f"SMS sent successfully to {to} with SID: {message.sid}")
            return message.sid
        except Exception as error:
            application_logger.error(f"Failed to send SMS to {to}: {error}", exc_info=True)
            raise SMSManagerError(f"Failed to send SMS to {to}: {error}")


@shared_task(bind=True, retry_backoff=True, max_retries=3)
def send_sms_task(self, to: str, body: str) -> str:
    """
    Sends an SMS asynchronously using Celery, leveraging the SMSManager.

    Args:
        self (celery.Task): The Celery task instance.
        to (str): Recipient's phone number (in E.164 format).
        body (str): SMS message body.

    Returns:
        str: Message SID.

    Raises:
        Exception: If an error occurs during SMS sending, the task will be retried with exponential backoff.
    """
    try:
        message_sid = SMSManager.send_sms(to=to, body=body)
        application_logger.info(f"SMS sent successfully to {to} with SID: {message_sid}")
        return message_sid
    except Exception as exc:
        application_logger.error(f"Error sending SMS to {to}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)  # Retry with exponential backoff
