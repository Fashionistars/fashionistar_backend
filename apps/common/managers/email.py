# apps/common/managers/email.py

import logging
import asyncio
from typing import Any, List, Optional
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist

logger = logging.getLogger('application')

class EmailManagerError(Exception):
    """Raise an exception if an error occurs in the email manager"""

class EmailManager:
    """
    Manages email sending with sync and async methods.
    """
    max_attempts = 3

    @classmethod
    def send_mail(cls, subject: str, recipients: List[str], context: Optional[dict[str, Any]] = None, template_name: Optional[str] = None, message: Optional[str] = None, attachments: Optional[List[tuple]] = None, fail_silently: bool = False) -> None:
        """
        Send email (sync).
        """
        try:
            if (context and template_name is None) or (template_name and context is None):
                raise EmailManagerError("context set but template_name not set Or template_name set and context not set.")
            if (context is None) and (template_name is None) and (message is None):
                raise EmailManagerError("Must set either {context and template_name} or message args.")
            html_message = None
            plain_message = message
            if context and template_name:
                html_message = render_to_string(template_name=template_name, context=context)
                plain_template_name = template_name.replace(".html", ".txt")
                try:
                    plain_message = render_to_string(plain_template_name, context=context)
                except TemplateDoesNotExist:
                    logger.warning(f"Plain text template missing: {plain_template_name}")
                    plain_message = html_message
            email = EmailMultiAlternatives(subject=subject, body=plain_message or '', from_email=settings.DEFAULT_FROM_EMAIL, to=recipients)
            if html_message:
                email.attach_alternative(html_message, "text/html")
            if attachments:
                for filename, content, mimetype in attachments:
                    email.attach(filename, content, mimetype)
            email.send(fail_silently=fail_silently)
            logger.info(f"Email sent to {recipients}")
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            raise

    @classmethod
    async def asend_mail(cls, subject: str, recipients: List[str], context: Optional[dict[str, Any]] = None, template_name: Optional[str] = None, message: Optional[str] = None, attachments: Optional[List[tuple]] = None, fail_silently: bool = False) -> None:
        """
        Send email (async).
        """
        try:
            # Run sync email sending in a thread to avoid blocking the event loop
            await asyncio.to_thread(
                cls.send_mail,
                subject, recipients, context, template_name, message, attachments, fail_silently
            )
            logger.info(f"Email sent (async) to {recipients}")
        except Exception as e:
            logger.error(f"Error sending email (async): {str(e)}")
            raise

    @classmethod
    def bulk_send_mail(cls, email_messages: List[dict[str, Any]], fail_silently: bool = False) -> None:
        """
        Sends multiple emails in bulk (Synchronous/Blocking).

        This method processes a list of email message dictionaries, constructing and dispatching
        each EmailMultiAlternatives object. It supports batch sending with comprehensive error handling.

        Args:
            email_messages (List[dict[str, Any]]): A list of dictionaries, each containing:
                - 'subject' (str): The subject line of the email.
                - 'recipients' (List[str]): List of recipient email addresses.
                - 'context' (Optional[dict[str, Any]]): Data for template rendering.
                - 'template_name' (Optional[str]): Path to the HTML template.
                - 'message' (Optional[str]): Plain text message (mutually exclusive with template).
                - 'attachments' (Optional[List[tuple]]): List of (filename, content, mimetype) tuples.
            fail_silently (bool): If True, suppresses exceptions (default: False).

        Raises:
            EmailManagerError: If invalid arguments are provided for any message.
            TemplateDoesNotExist: If a specified template is invalid.
            Exception: Any underlying error from the email backend provider.
        """
        try:
            for email_data in email_messages:
                # Extract parameters with defaults
                subject = email_data.get('subject')
                recipients = email_data.get('recipients', [])
                context = email_data.get('context')
                template_name = email_data.get('template_name')
                message = email_data.get('message')
                attachments = email_data.get('attachments')

                # Validate required fields
                if not subject or not recipients:
                    raise EmailManagerError("Each email message must have 'subject' and 'recipients'.")

                # Send individual email
                cls.send_mail(
                    subject=subject,
                    recipients=recipients,
                    context=context,
                    template_name=template_name,
                    message=message,
                    attachments=attachments,
                    fail_silently=fail_silently
                )

            logger.info(f"✅ Bulk email sending completed: {len(email_messages)} messages sent.")

        except Exception as e:
            logger.error(f"❌ Error in bulk email sending: {e}", exc_info=True)
            if not fail_silently:
                raise

    @classmethod
    async def abulk_send_mail(cls, email_messages: List[dict[str, Any]], fail_silently: bool = False) -> None:
        """
        Sends multiple emails in bulk asynchronously (Non-Blocking).

        This method wraps the synchronous bulk_send_mail in asyncio.to_thread to prevent
        blocking the event loop during batch email operations.

        Args:
            email_messages (List[dict[str, Any]]): Same as bulk_send_mail.
            fail_silently (bool): Same as bulk_send_mail.

        Returns:
            None
        """
        try:
            # Offload the blocking bulk operation to a worker thread
            await asyncio.to_thread(
                cls.bulk_send_mail,
                email_messages=email_messages,
                fail_silently=fail_silently
            )
            logger.info(f"✅ Bulk email sent (async): {len(email_messages)} messages.")
        except Exception as e:
            logger.error(f"❌ Error in async bulk email sending: {e}", exc_info=True)
            if not fail_silently:
                raise