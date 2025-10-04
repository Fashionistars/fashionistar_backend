# userauths/task.py

from celery import shared_task
import logging
from django.conf import settings
from django.template.exceptions import TemplateDoesNotExist

from utilities.managers.email import EmailManager  # Import your EmailManager
from utilities.managers.sms import SMSManager  # Import your SMSManager

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
