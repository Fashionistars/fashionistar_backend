# apps/common/managers/email.py

import logging
import asyncio
from typing import Any, List, Optional, Tuple

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist

# -----------------------------------------------------------------------------
# Logger Configuration
# -----------------------------------------------------------------------------
# We initialize the 'application' logger to ensure all email operations are 
# tracked centrally in the application's log files.
Logger = logging.getLogger('application')


class EmailManagerError(Exception):
    """
    Custom Exception for Email Manager.
    
    This exception is raised when critical errors occur during:
    1. Template rendering (e.g., TemplateDoesNotExist).
    2. Email dispatch (e.g., SMTPConnectionError).
    3. Argument validation (e.g., missing template or context).
    
    Using a custom exception allows the calling views/services to catch 
    email-specific failures distinct from general application errors.
    """
    pass


class EmailManager:
    """
    Centralized Email Manager for handling all email communications.
    
    ---------------------------------------------------------------------------
    Architectural Overview:
    ---------------------------------------------------------------------------
    This manager serves as a unified Facade for the Django Email System. 
    It abstracts away the complexities of:
    1.  **Template Rendering**: Automatically renders HTML templates and attempts 
        to find/render a plain-text fallback counterpart (.txt).
    2.  **Dynamic Backend Selection**: It leans on the configured `EMAIL_BACKEND` 
        setting (which points to our `DatabaseConfiguredEmailBackend`), allowing
        administrators to switch providers (SMTP, Mailgun, SendGrid) without code changes.
    3.  **Asynchronous Execution**: Provides native `async` methods (`asend_mail`) 
        that leverage `asyncio.to_thread` to prevent blocking the Main Event Loop 
        during I/O-heavy SMTP operations.
    4.  **Bulk / Mass Sending**: Provides optimized methods for sending batch emails.
    
    Attributes:
        max_attempts (int): The number of retries for failed sends (future implementation).
    """
    
    max_attempts = 3 

    # =========================================================================
    # Synchronous Single Email Method
    # =========================================================================

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
        Sends a single email immediately (Synchronous/Blocking).
        
        This method is the workhorse for standard email dispatch. It validates inputs,
        renders templates (HTML + Text), handles attachments, and pushes the email 
        connection.
        
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
            Exception: Any underlying error from the email backend provider (if fail_silently=False).
        """
        
        # ---------------------------------------------------------------------
        # 1. Argument Validation
        # ---------------------------------------------------------------------
        # We must ensure that the caller has provided either a raw message OR
        # a template + context pair. They cannot provide one without the other
        # where dependencies exist.
        if (context and template_name is None) or (template_name and context is None):
            error_msg = "Invalid Arguments: You must provide both 'context' and 'template_name' together."
            Logger.error(error_msg)
            raise EmailManagerError(error_msg)
            
        if (context is None) and (template_name is None) and (message is None):
            error_msg = "Invalid Arguments: You must provide either a 'message' string OR a 'template_name' with 'context'."
            Logger.error(error_msg)
            raise EmailManagerError(error_msg)

        html_message: str | None = None
        plain_message: str | None = message

        # ---------------------------------------------------------------------
        # 2. Template Rendering Logic
        # ---------------------------------------------------------------------
        if context is not None and template_name:
            try:
                # Render the main HTML content
                # This uses Django's template engine to process variables/tags
                html_message = render_to_string(template_name=template_name, context=context)
                
                # Dynamic Plain Text Fallback
                # We attempt to find a .txt version of the same template file.
                # e.g., 'welcome.html' -> 'welcome.txt'
                plain_template_name = template_name.replace(".html", ".txt")
                
                try:
                    plain_message = render_to_string(plain_template_name, context=context)
                except TemplateDoesNotExist:
                    # If no .txt template exists, we log a warning but proceed.
                    # Some clients effectively strip HTML tags, but providing a native 
                    # fallback is best practice for spam scores and accessibility.
                    Logger.warning(f"⚠️ Plain text template missing: {plain_template_name}. Using HTML content as fallback plain text.")
                    plain_message = html_message 

            except TemplateDoesNotExist as error:
                Logger.error(f"❌ Template not found: {template_name}")
                raise EmailManagerError(f"Template not found: {template_name}") from error
            except Exception as e:
                Logger.error(f"❌ Error rendering email template {template_name}: {e}")
                raise EmailManagerError(f"Error rendering template: {e}") from e

        # ---------------------------------------------------------------------
        # 3. Email Dispatch
        # ---------------------------------------------------------------------
        try:
            # Construct the EmailMultiAlternatives Object
            # We rely on settings.DEFAULT_FROM_EMAIL to ensure sender consistency.
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_message or '',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients
            )

            # Attach HTML alternative if we successfully rendered it
            if html_message:
                email.attach_alternative(html_message, "text/html")

            # Process Attachments if any provided
            if attachments:
                for filename, content, mimetype in attachments:
                    email.attach(filename, content, mimetype)

            # Send via the configured Backend
            # backend logic handles the actual protocol (SMTP, API, etc.)
            email.send(fail_silently=fail_silently)
            
            Logger.info(f"✅ Email sent successfully to {recipients}")
            
        except Exception as error:
            Logger.error(f"❌ Error sending email to {recipients}: {error}", exc_info=True)
            if not fail_silently:
                # Re-raise the exception so the caller knows something went wrong
                raise

    # =========================================================================
    # Asynchronous Single Email Method
    # =========================================================================

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
        
        This method is a wrapper around the synchronous `send_mail` method.
        It utilizes `asyncio.to_thread` to offload the blocking I/O operation 
        (network socket to SMTP server) to a separate worker thread.
        
        Why is this necessary?
        Django's async views run on a single Event Loop. If we performed a blocking
        SMTP call directly in the main thread, the entire server would freeze 
        for all users until that email finished sending.
        
        Args:
            Same arguments as `send_mail`.
            
        Returns:
            None
        """
        try:
            # Delegating the blocking call to a thread pool
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
        except Exception as e:
            # Catching thread-boundary errors explicitly
            Logger.error(f"❌ Async Email Send Error to {recipients}: {e}", exc_info=True)
            if not fail_silently:
                raise

    # =========================================================================
    # Synchronous Bulk / Mass Email Method
    # =========================================================================

    @classmethod
    def send_mass_mail(cls, datatuple: Tuple[Tuple], fail_silently: bool = False) -> int:
        """
        Sends multiple distinct emails in a single connection batch (Synchronous).
        
        This method corresponds to Django's native `send_mass_mail`. It is highly 
        optimized for sending many emails (like newsletters or notifications) 
        because it opens a single connection to the mail server and pipelines 
        the messages, rather than opening/closing a connection for each one.
        
        Args:
            datatuple: A tuple of message tuples. Each message tuple should contain:
                       (subject, message, sender, recipient_list).
            fail_silently: If True, connection errors will be suppressed.

        Returns:
            int: The number of messages successfully delivered.
        """
        from django.core.mail import send_mass_mail as django_mass_mail
        
        try:
            Logger.info(f"🚀 Starting bulk email send. Batch size: {len(datatuple)} messages.")
            
            # Note on Backend: This call will utilize our globally configured 
            # EMAIL_BACKEND (DatabaseConfiguredEmailBackend).
            # The backend is responsible for handling the connection reuse.
            count = django_mass_mail(datatuple, fail_silently=fail_silently)
            
            Logger.info(f"✅ Bulk email send completed successfully. Sent: {count}/{len(datatuple)}")
            return count
            
        except Exception as e:
            Logger.error(f"❌ Error in send_mass_mail batch: {e}", exc_info=True)
            if not fail_silently:
                raise
            return 0

    # =========================================================================
    # Asynchronous Bulk / Mass Email Method
    # =========================================================================

    @classmethod
    async def asend_mass_mail(cls, datatuple: Tuple[Tuple], fail_silently: bool = False) -> int:
        """
        Sends multiple distinct emails asynchronously (Non-Blocking).
        
        This is the **Async** counterpart for bulk email sending.
        It wraps `send_mass_mail` in `asyncio.to_thread` to ensure the 
        blocking mass-send operation does not halt the async event loop.
        
        Usage:
            await EmailManager.asend_mass_mail(messages_tuple)
            
        Args:
            datatuple: Tuple of message tuples (see send_mass_mail).
            fail_silently: Boolean to suppress errors.
            
        Returns:
            int: Number of messages sent.
        """
        try:
            # Offloading to worker thread
            return await asyncio.to_thread(
                cls.send_mass_mail, 
                datatuple, 
                fail_silently
            )
        except Exception as e:
            Logger.error(f"❌ Error in asend_mass_mail: {e}", exc_info=True)
            if not fail_silently:
                raise
            return 0