# apps/common/managers/email
import logging
import os
import time
from typing import Any, List, Optional
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist
from django.utils import timezone
from asgiref.sync import sync_to_async

Logger = logging.getLogger('application')


class EmailManagerError(Exception):
    """Raise an exception if an error occurs in the email manager"""


class EmailManager:
    """
    Manages the sending of emails, including handling template rendering and attachments.
    Supports both Sync and Async operations.
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
        Sends email to valid email addresses immediately (SYNC).

        Args:
            subject (str): The subject of the email.
            recipients (List[str]): A list of recipient email addresses.
            context (Optional[dict[str, Any]]): A dictionary of context data for rendering the email template.
            template_name (Optional[str]): The path to the HTML email template.
            message (Optional[str]): A plain text email message if not using a template.
            attachments (Optional[List[tuple]]): A list of tuples containing attachment filename, content, and mimetype.
            fail_silently (bool): Whether to suppress exceptions.

        Raises:
            EmailManagerError: If context/template config is invalid.
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

    @classmethod
    async def asend_mail(
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
        Async wrapper for send_mail.
        """
        return await sync_to_async(cls.send_mail)(
            subject=subject,
            recipients=recipients,
            context=context,
            template_name=template_name,
            message=message,
            attachments=attachments,
            fail_silently=fail_silently
        )