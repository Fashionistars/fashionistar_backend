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

logger = logging.getLogger(__name__)


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


# ================================================================
# 3. MODEL ANALYTICS COUNTER (Background atomic update)
# ================================================================

@shared_task(
    name="update_model_analytics_counter",
    bind=True,
    max_retries=0,        # Fire-and-forget: no retries to stay fast
    ignore_result=True,
)
def update_model_analytics_counter(self, model_name, app_label, deltas):
    """
    Atomically update the ``ModelAnalytics`` row for
    ``model_name`` with the given ``deltas``.

    Runs as a fire-and-forget background task so the HTTP
    request / admin action that triggered it is NOT delayed.

    Uses ``SELECT ... FOR UPDATE`` inside ``transaction.atomic()``
    (via ``ModelAnalytics._adjust()``) to eliminate race
    conditions under high concurrency.

    Args:
        model_name (str): The Django model class name.
        app_label (str): The Django app label.
        deltas (dict): Mapping of field name → integer delta.
            Example: ``{'total_created': 1, 'total_active': 1}``

    Design notes
    ------------
    * max_retries=0 + ignore_result=True = true fire-and-forget.
    * If Celery/Redis is down when the task is dispatched,
      ``ModelAnalytics._dispatch()`` falls back to a synchronous
      ``_adjust()`` call, so counts are never permanently lost.
    * The ``select_for_update()`` lock is held only for the
      duration of the single UPDATE statement (~1ms) so
      throughput impact is negligible.
    """
    try:
        from apps.common.models import ModelAnalytics
        ModelAnalytics._adjust(
            model_name=model_name,
            app_label=app_label,
            **deltas,
        )
        logger.debug(
            "ModelAnalytics updated for %s: %s",
            model_name,
            deltas,
        )
    except Exception:
        logger.warning(
            "update_model_analytics_counter failed for %s: %s",
            model_name,
            deltas,
        )

# ================================================================
# 4. CLOUDINARY BACKGROUND TASKS
# ================================================================


@shared_task(
    name="delete_cloudinary_asset_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    ignore_result=True,
)
def delete_cloudinary_asset_task(self, public_id, resource_type="image"):
    """
    Deletes an asset from Cloudinary in the background.

    Dispatched as a Celery background task to make Cloudinary
    deletes non-blocking during model updates or deletes.
    """
    from apps.common.utils import delete_cloudinary_asset
    try:
        result = delete_cloudinary_asset(
            public_id,
            resource_type=resource_type
        )
        if result and result.get('result') == 'ok':
            logger.info(
                "Background deletion of Cloudinary asset %s successful.",
                public_id
            )
        else:
            logger.warning(
                "Background deletion of Cloudinary asset %s returned: %s",
                public_id,
                result
            )
    except Exception as exc:
        logger.error(
            "Failed to delete Cloudinary asset %s: %s",
            public_id,
            exc
        )
        raise self.retry(exc=exc)


# ================================================================
# 5. USER LIFECYCLE REGISTRY — Background Task
# ================================================================

@shared_task(
    name="upsert_user_lifecycle_registry",
    bind=True,
    max_retries=1,
    default_retry_delay=10,
    ignore_result=True,
)
def upsert_user_lifecycle_registry(
    self,
    user_uuid,
    action,               # 'created' | 'soft_deleted' | 'hard_deleted' | 'restored'
    email=None,
    phone=None,
    member_id='',
    role='',
    auth_provider='email',
    country=None,
    state=None,
    city=None,
    ip_address=None,
    source='web',
):
    """
    Upsert a ``UserLifecycleRegistry`` row for the given ``user_uuid``.

    Called from the UnifiedUser post-save signal and from the
    soft_delete / hard_delete lifecycle hooks via ``transaction.on_commit``
    so this NEVER blocks the HTTP request / admin action path.

    Actions
    -------
    * ``created``      — creates the row with status='active'.
    * ``soft_deleted`` — sets status='soft_deleted', soft_deleted_at=now.
    * ``hard_deleted`` — sets status='hard_deleted', hard_deleted_at=now.
    * ``restored``     — sets status='active',       restored_at=now.

    Design
    ------
    Uses ``update_or_create`` keyed on ``user_uuid`` so re-runs are safe
    (idempotent). The registry row is NEVER deleted by this task.
    """
    from django.utils import timezone
    from apps.common.models import UserLifecycleRegistry
    import uuid

    try:
        now = timezone.now()

        if action == 'created':
            UserLifecycleRegistry.objects.get_or_create(
                user_uuid=uuid.UUID(str(user_uuid)),
                defaults=dict(
                    email=email,
                    phone=phone,
                    member_id=member_id or '',
                    role=role or '',
                    auth_provider=auth_provider or 'email',
                    country=country,
                    state=state,
                    city=city,
                    ip_address=ip_address,
                    source=source or 'web',
                    status=UserLifecycleRegistry.STATUS_ACTIVE,
                ),
            )
            logger.info(
                "UserLifecycleRegistry: created entry for user_uuid=%s (%s)",
                user_uuid, email or phone,
            )

        elif action == 'soft_deleted':
            updated = UserLifecycleRegistry.objects.filter(
                user_uuid=uuid.UUID(str(user_uuid)),
            ).update(
                status=UserLifecycleRegistry.STATUS_SOFT_DELETED,
                soft_deleted_at=now,
            )
            if updated == 0:
                logger.warning(
                    "UserLifecycleRegistry: no row found for soft_deleted user_uuid=%s",
                    user_uuid,
                )

        elif action == 'hard_deleted':
            updated = UserLifecycleRegistry.objects.filter(
                user_uuid=uuid.UUID(str(user_uuid)),
            ).update(
                status=UserLifecycleRegistry.STATUS_HARD_DELETED,
                hard_deleted_at=now,
            )
            if updated == 0:
                logger.warning(
                    "UserLifecycleRegistry: no row found for hard_deleted user_uuid=%s",
                    user_uuid,
                )

        elif action == 'restored':
            UserLifecycleRegistry.objects.filter(
                user_uuid=uuid.UUID(str(user_uuid)),
            ).update(
                status=UserLifecycleRegistry.STATUS_ACTIVE,
                restored_at=now,
                soft_deleted_at=None,   # Clear soft-delete timestamp on restore
            )

        else:
            logger.warning(
                "upsert_user_lifecycle_registry: unknown action=%s for user_uuid=%s",
                action, user_uuid,
            )

    except Exception as exc:
        logger.exception(
            "upsert_user_lifecycle_registry FAILED for user_uuid=%s action=%s: %s",
            user_uuid, action, exc,
        )
        raise self.retry(exc=exc)


@shared_task(
    name="increment_lifecycle_login_counter",
    bind=True,
    max_retries=1,
    default_retry_delay=5,
    ignore_result=True,
)
def increment_lifecycle_login_counter(self, user_uuid, login_at=None):
    """
    Atomically increment ``total_logins`` and update ``last_login_at``
    in ``UserLifecycleRegistry`` for the given ``user_uuid``.

    Called from the login service after a successful authentication,
    wrapped in ``transaction.on_commit`` so it never blocks the response.

    Args:
        user_uuid (str): The UnifiedUser PK as a string.
        login_at  (str|None): ISO timestamp of the login. Defaults to now.
    """
    from django.db.models import F
    from django.utils import timezone
    from apps.common.models import UserLifecycleRegistry
    import uuid

    try:
        uid  = uuid.UUID(str(user_uuid))
        when = timezone.now() if login_at is None else login_at

        UserLifecycleRegistry.objects.filter(user_uuid=uid).update(
            total_logins=F('total_logins') + 1,
            last_login_at=when,
        )
        logger.debug(
            "UserLifecycleRegistry: login counter incremented for user_uuid=%s",
            user_uuid,
        )
    except Exception as exc:
        logger.warning(
            "increment_lifecycle_login_counter failed for user_uuid=%s: %s",
            user_uuid, exc,
        )
        raise self.retry(exc=exc)

