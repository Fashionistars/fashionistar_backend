# apps/authentication/tasks.py
"""
Celery Tasks for Authentication Module.

These tasks offload I/O-heavy operations (email, SMS) to background workers,
preventing request/response cycles from blocking on SMTP or HTTP calls.

Architecture:
    - send_email_task: Dispatches templated emails via EmailManager.
    - send_sms_task: Dispatches SMS messages via SMSManager.

Both tasks use exponential backoff with max 3 retries.
"""

from celery import shared_task
import logging
from django.template.exceptions import TemplateDoesNotExist

# ── Corrected import paths (apps.common, not utilities) ─────────────
from apps.common.managers.email import EmailManager, EmailManagerError
from apps.common.managers.sms import SMSManager

# Per-module logger — auto-routes to logs/apps/authentication/auth.log
logger = logging.getLogger(__name__)

@shared_task(bind=True, retry_backoff=True, max_retries=3)
def send_email_task(
    self,
    subject: str,
    recipients: list[str],
    template_name: str,
    context: dict,
    attachments: list[tuple] | None = None,
) -> str:
    """
    Sends an email asynchronously using Celery, leveraging the EmailManager.
    Handles potential template errors and retries.

    DEBUG mode: when settings.DEBUG=True, the rendered HTML body is logged
    to the Celery worker terminal at DEBUG level for live template inspection.
    This makes it easy to verify email template rendering without a real SMTP
    server — just watch the `make celery` terminal.

    Args:
        self:          The Celery task instance.
        subject:       Email subject.
        recipients:    List of recipient email addresses.
        template_name: Path to the HTML email template.
        context:       Dictionary of data to pass to the template.
        attachments:   Optional list of (filename, content, mimetype) tuples.

    Returns:
        str: A success message, or raises an exception on failure.
    """
    try:
        logger.info(
            "📧 [Celery] Sending email\n"
            "  ├── template  : %s\n"
            "  ├── subject   : %s\n"
            "  └── recipients: %s",
            template_name, subject, recipients,
        )

        # ── DEBUG: render and print template to Celery terminal ──────────
        # This makes it trivial to verify template context / rendering
        # without needing a real SMTP server or Mailgun/SendGrid sandbox.
        from django.conf import settings as _settings
        if getattr(_settings, 'DEBUG', False):
            try:
                from django.template.loader import render_to_string
                rendered = render_to_string(template_name=template_name, context=context)
                logger.debug(
                    "📄 [Celery][DEBUG] Template rendered — %s\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "%s\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                    template_name,
                    rendered[:4000],  # cap at 4000 chars to avoid log flooding
                )
            except Exception as render_exc:
                logger.warning("[Celery][DEBUG] Could not pre-render template for logging: %s", render_exc)

        EmailManager.send_mail(
            subject=subject,
            recipients=recipients,
            template_name=template_name,
            context=context,
            attachments=attachments,
        )
        logger.info(
            "✅ [Celery] Email sent successfully\n"
            "  ├── template  : %s\n"
            "  └── recipients: %s",
            template_name, recipients,
        )
        return f"Email sent successfully to {recipients}"

    except (TemplateDoesNotExist, EmailManagerError) as exc:
        # Template missing or invalid args — retrying won't help.
        logger.error(
            "🚨 [Celery] Template/config error: %s — %s",
            template_name, exc, exc_info=True,
        )
        raise  # Fail the task permanently — no retry

    except Exception as exc:
        logger.warning(
            "⚠️ [Celery] Email send failed (attempt %s/%s) → %s: %s",
            self.request.retries + 1, self.max_retries + 1, recipients, exc,
        )
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))



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
        logger.info("📱 [Celery] Sending SMS → to=%s", to)
        message_sid = SMSManager.send_sms(to=to, body=body)
        logger.info("✅ [Celery] SMS sent → %s (SID: %s)", to, message_sid)
        return message_sid
    except Exception as exc:
        logger.warning(
            "⚠️ [Celery] SMS send failed (attempt %s/%s) → %s: %s",
            self.request.retries + 1, self.max_retries + 1, to, exc
        )
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@shared_task(bind=True, retry_backoff=True, max_retries=5, name='authentication.upload_google_avatar_to_cloudinary')
def upload_google_avatar_to_cloudinary(self, user_pk: str, google_avatar_url: str) -> str:
    """
    Download a Google profile picture and upload it to our Cloudinary account.

    This task is triggered on_commit after a new Google OAuth registration.
    It replaces the raw Google CDN URL (which can become inaccessible if the
    user revokes Google token access) with a permanent Cloudinary HTTPS URL
    that we control.

    Flow:
      1. Download the image from Google's CDN (plain HTTP GET).
      2. Upload the raw bytes to Cloudinary under the ``avatars/`` folder,
         using the user's member_id as the public_id for de-duplication.
      3. Update ``user.avatar`` with the Cloudinary secure_url.

    Args:
        user_pk:           UUID string of the UnifiedUser PK.
        google_avatar_url: The ``picture`` field from the Google ID-token payload.

    Returns:
        str: The Cloudinary secure_url stored on the user.
    """
    import urllib.request
    import io

    try:
        from apps.authentication.models import UnifiedUser

        logger.info(
            "📸 [Celery] upload_google_avatar: user_pk=%s url=%s",
            user_pk, google_avatar_url,
        )

        # ── 1. Fetch the user ───────────────────────────────────────────
        try:
            user = UnifiedUser.objects.get(pk=user_pk)
        except UnifiedUser.DoesNotExist:
            logger.error(
                "❌ upload_google_avatar: user_pk=%s not found — giving up.", user_pk
            )
            return "user_not_found"

        # ── 2. Download avatar bytes from Google CDN ────────────────────
        try:
            # Add =s400 to request a 400px version from Google's image API
            sized_url = google_avatar_url
            if '=' not in google_avatar_url:
                sized_url = google_avatar_url + '=s400'

            req = urllib.request.Request(
                sized_url,
                headers={'User-Agent': 'Fashionistar/1.0 AvatarFetcher'},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                image_bytes = resp.read()
                # Content-Type reserved for future format-specific handling
                _ = resp.headers.get('Content-Type', 'image/jpeg')
        except Exception as dl_exc:
            logger.warning(
                "⚠️ upload_google_avatar: download failed for %s: %s", user_pk, dl_exc
            )
            raise self.retry(exc=dl_exc)

        # ── 3. Upload to Cloudinary ─────────────────────────────────────
        try:
            import cloudinary
            import cloudinary.uploader
            from apps.common.tasks.cloudinary import _ensure_cloudinary_config
            
            _ensure_cloudinary_config()

            # Use member_id as public_id so re-uploads replace the same file
            public_id = f"avatars/google_{user.member_id or str(user.pk)[:8]}"

            result = cloudinary.uploader.upload(
                io.BytesIO(image_bytes),
                public_id=public_id,
                folder="fashionistar/avatars",
                overwrite=True,
                resource_type="image",
                format="webp",                  # Transcode to WebP for bandwidth savings
                transformation=[
                    {"width": 400, "height": 400, "crop": "fill", "gravity": "face"},
                    {"quality": "auto", "fetch_format": "auto"},
                ],
                tags=["google_avatar", "user_avatar"],
            )
            cloudinary_url = result.get('secure_url', '')
        except Exception as cl_exc:
            logger.warning(
                "⚠️ upload_google_avatar: Cloudinary upload failed for %s: %s",
                user_pk, cl_exc,
            )
            raise self.retry(exc=cl_exc)

        # ── 4. Persist the Cloudinary URL on the user ───────────────────
        if cloudinary_url:
            UnifiedUser.objects.filter(pk=user_pk).update(avatar=cloudinary_url)
            logger.info(
                "✅ [Celery] Google avatar uploaded to Cloudinary for user=%s → %s",
                user_pk, cloudinary_url,
            )
            return cloudinary_url
        else:
            logger.warning(
                "⚠️ upload_google_avatar: Cloudinary returned empty URL for user=%s", user_pk
            )
            return "empty_url"

    except Exception as exc:
        logger.error(
            "❌ [Celery] upload_google_avatar fatal error for user=%s: %s",
            user_pk, exc, exc_info=True,
        )
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

