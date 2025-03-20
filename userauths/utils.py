import logging
import os
import time
from typing import Any, List, Optional
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist
from django.utils import timezone
from celery import shared_task
from django.conf import settings
from twilio.rest import Client  # Import the Twilio Client

Logger = logging.getLogger('application')


class EmailManagerError(Exception):
    """Raise an exception if an error occurs in the email manager"""


class EmailManager:
    """
    Manages the sending of emails, including handling template rendering and attachments.
    """
    max_attempts = 3  # retry logic

    @classmethod
    def send_mail(
        cls,
        subject: str,
        recipients: List[str],
        context: Optional[dict[str, Any]] = None,
        template_name: Optional[str] = None,
        message: Optional[str] = None,
        attachments: Optional[List[tuple]] = None,
        fail_silently: bool = False
    ) -> None:
        """
        Sends email to valid email addresses immediately.

        Args:
            subject (str): The subject of the email.
            recipients (List[str]): A list of recipient email addresses.
            context (Optional[dict[str, Any]]): A dictionary of context data for rendering the email template.
            template_name (Optional[str]): The path to the HTML email template.
            message (Optional[str]): A plain text email message if not using a template.
            attachments (Optional[List[tuple]]): A list of tuples containing attachment filename, content, and mimetype.
            fail_silently (bool): Whether to suppress exceptions.

        Raises:
            EmailManagerError: If context and template_name are not both set, or if neither context/template_name nor message is set.
            TemplateDoesNotExist: If the specified template does not exist.
            Exception: If an error occurs during email sending.
        """
        if (context and template_name is None) or (template_name and context is None):
            raise EmailManagerError(
                "context set but template_name not set Or template_name set and context not set."
            )
        if (context is None) and (template_name is None) and (message is None):
            raise EmailManagerError(
                "Must set either {context and template_name} or message args."
            )

        html_message: str | None = None
        plain_message: str | None = message

        if context is not None and template_name:
            try:
                html_message = render_to_string(template_name=template_name, context=context)
                # Construct the text template name dynamically
                plain_template_name = template_name.replace(".html", ".txt")
                try:
                    plain_message = render_to_string(plain_template_name, context=context)
                except TemplateDoesNotExist:
                    Logger.warning(f"⚠️ Plain text template missing / not found: {plain_template_name}. Using HTML as fallback.")
                    plain_message = html_message  # Fallback to HTML if plain text version is missing

            except TemplateDoesNotExist as error:
                raise EmailManagerError from error

        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_message or '',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )

            if html_message:
                email.attach_alternative(html_message, "text/html")

            if attachments:
                for filename, content, mimetype in attachments:
                    email.attach(filename, content, mimetype)

            email.send(fail_silently=fail_silently)  # SEND IMMEDIATELY
            Logger.info(f"✅ Email sent successfully to {recipients}")
        except Exception as error:
            Logger.error(f"Error sending email to {recipients}: {error}", exc_info=True)
            raise





@shared_task(bind=True, retry_backoff=True, max_retries=5)
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
        raise  # Re-raise the exception to prevent retry, as the template issue won't resolve itself.  Fix template error!

    except Exception as exc:
        application_logger.exception(f"❌ Error sending email to {recipients}, retrying... Error: {exc}")  # Use exception for full traceback
        # Retry the task with exponential backoff.
        raise self.retry(exc=exc, countdown=60)

























# @shared_task(bind=True, retry_backoff=True, max_retries=5)
# def process_email_queue_task(self):
#     """
#     Processes emails from the email queue.

#     This task is designed to run periodically and send emails stored in the email queue.
#     If an error occurs during the processing of emails, it will be retried with exponential backoff.

#     Args:
#         self (celery.Task): The Celery task instance.

#     Returns:
#         str: A success message or raises an exception on failure.

#     Raises:
#         Exception: If an error occurs while processing the email queue, the task will be retried with exponential backoff.
#     """
#     try:
#         application_logger.info("⚙️ Starting email queue processing...")
#         # No email Queue implementation here
#         application_logger.info("✅ Email queue processing completed.")
#         return "Email queue processing completed successfully."
#     except Exception as exc:
#         application_logger.exception(f"❌ Error processing email queue: {exc}")
#         raise self.retry(exc=exc, countdown=60)  # Retry with exponential backoff







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
            Logger.info(f"SMS sent successfully to {to} with SID: {message.sid}")
            return message.sid
        except Exception as error:
            Logger.error(f"Failed to send SMS to {to}: {error}", exc_info=True)
            raise SMSManagerError(f"Failed to send SMS to {to}: {error}")


@shared_task(bind=True, retry_backoff=True, max_retries=5)
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