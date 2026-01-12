# apps/common/managers/email.py
import logging
import asyncio
from typing import Any, List, Optional
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist

# Initialize application logger for detailed tracking of email operations
Logger = logging.getLogger('application')


class EmailManagerError(Exception):
    """
    Custom Exception for Email Manager.
    Raised when critical errors occur during template rendering or email dispatch.
    """
    pass


class EmailManager:
    """
    Centralized Email Manager for handling all email communications.
    
    Features:
    - Supports both Synchronous and Asynchronous execution (via asyncio.to_thread).
    - Robust Template Rendering (HTML with Plain Text fallback).
    - Attachment Handling.
    - Dynamic Backend Selection (handled transparently by admin_backend's DatabaseConfiguredEmailBackend).
    
    This manager abstracts the complexity of email composition and sending, providing
    a clean interface for the rest of the application.
    """
    
    # Retry logic configuration (if implemented in future versions)
    max_attempts = 3 

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
        Sends an email immediately (Synchronous/Blocking).
        
        This method constructs an EmailMultiAlternatives object, renders the HTML template
        (and attempts to render a corresponding .txt plain text version), handles attachments,
        and dispatches the email using the configured backend.
        
        Args:
            subject (str): The subject line of the email.
            recipients (List[str]): A list of recipient email addresses.
            context (Optional[dict[str, Any]]): Dictionary of data to render in the template.
            template_name (Optional[str]): Path to the HTML template (e.g., 'emails/welcome.html').
            message (Optional[str]): Explicit plain text message (mutually exclusive with template/context).
            attachments (Optional[List[tuple]]): List of (filename, content, mimetype) tuples.
            fail_silently (bool): If True, suppresses exceptions (default: False).
            
        Raises:
            EmailManagerError: If invalid arguments are provided (e.g., context without template).
            TemplateDoesNotExist: If the specified template path is invalid.
            Exception: Any underlying error from the email backend provider.
        """
        # Validate arguments: Ensure valid combination of message vs template
        if (context and template_name is None) or (template_name and context is None):
            raise EmailManagerError(
                "Invalid Arguments: You must provide both 'context' and 'template_name' together."
            )
        if (context is None) and (template_name is None) and (message is None):
            raise EmailManagerError(
                "Invalid Arguments: You must provide either a 'message' string OR a 'template_name' with 'context'."
            )

        html_message: str | None = None
        plain_message: str | None = message

        # Template Rendering Logic
        if context is not None and template_name:
            try:
                # Render the main HTML content
                html_message = render_to_string(template_name=template_name, context=context)
                
                # Dynamic Plain Text Fallback: Try to find a .txt version of the same template
                plain_template_name = template_name.replace(".html", ".txt")
                try:
                    plain_message = render_to_string(plain_template_name, context=context)
                except TemplateDoesNotExist:
                    # If no .txt template exists, fallback to using the HTML content as text (or consider stripping tags)
                    Logger.warning(f"⚠️ Plain text template missing: {plain_template_name}. Using HTML content as fallback.")
                    plain_message = html_message 

            except TemplateDoesNotExist as error:
                Logger.error(f"Template not found: {template_name}")
                raise EmailManagerError(f"Template not found: {template_name}") from error

        try:
            # Construct the Email Object
            # Note: We rely on Django's default get_connection() which uses settings.EMAIL_BACKEND.
            # Our Admin Backend (admin_backend.backends.DatabaseConfiguredEmailBackend) is configured in settings.py
            # to handle the dynamic provider selection logic automatically.
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_message or '',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients
            )

            # Attach HTML alternative if available
            if html_message:
                email.attach_alternative(html_message, "text/html")

            # Process Attachments
            if attachments:
                for filename, content, mimetype in attachments:
                    email.attach(filename, content, mimetype)

            # Dispatch the email
            email.send(fail_silently=fail_silently)
            Logger.info(f"✅ Email sent successfully to {recipients}")
            
        except Exception as error:
            Logger.error(f"Error sending email to {recipients}: {error}", exc_info=True)
            if not fail_silently:
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
        Sends an email asynchronously (Non-Blocking).
        
        This method wraps the synchronous `send_mail` method in `asyncio.to_thread`.
        This is crucial for modern Async Django views, as standard SMTP operations are IO-blocking.
        Using a separate thread prevents the Main Async Event Loop from freezing while waiting for
        the email provider's response.
        
        Args:
            Same as send_mail.
            
        Returns:
            None
        """
        # Offload the blocking sync call to a worker thread
        return await asyncio.to_thread(
            cls.send_mail,
            subject=subject,
            recipients=recipients,
            context=context,
            template_name=template_name,
            message=message,
            attachments=attachments,
            fail_silently=fail_silently
        )