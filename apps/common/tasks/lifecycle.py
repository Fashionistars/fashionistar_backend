# apps/common/tasks/lifecycle.py
"""
User lifecycle registry Celery tasks.

Tasks:
    upsert_user_lifecycle_registry   — Create/update lifecycle row on user events.
    increment_lifecycle_login_counter — Atomically increment login counter.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


# ================================================================
# USER LIFECYCLE REGISTRY
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
    member_id="",
    role="",
    auth_provider="email",
    country=None,
    state=None,
    city=None,
    ip_address=None,
    source="web",
):
    """
    Upsert a ``UserLifecycleRegistry`` row for the given ``user_uuid``.

    Called from the UnifiedUser post-save signal and from the
    soft_delete / hard_delete lifecycle hooks via ``transaction.on_commit``
    so this NEVER blocks the HTTP request / admin action path.

    Actions:
        ``created``      — creates the row with status='active'.
        ``soft_deleted`` — sets status='soft_deleted', soft_deleted_at=now.
        ``hard_deleted`` — sets status='hard_deleted', hard_deleted_at=now.
        ``restored``     — sets status='active', restored_at=now.

    Design: Uses ``update_or_create`` keyed on ``user_uuid`` so re-runs
    are idempotent. The registry row is NEVER deleted by this task.
    """
    from django.utils import timezone
    from apps.common.models import UserLifecycleRegistry
    import uuid

    try:
        now = timezone.now()
        uid = uuid.UUID(str(user_uuid))

        if action == "created":
            try:
                obj, was_created = UserLifecycleRegistry.objects.get_or_create(
                    user_uuid=uid,
                    defaults=dict(
                        email=email,
                        phone=phone,
                        member_id=member_id or "",
                        role=role or "",
                        auth_provider=auth_provider or "email",
                        country=country,
                        state=state,
                        city=city,
                        ip_address=ip_address,
                        source=source or "web",
                        status=UserLifecycleRegistry.STATUS_ACTIVE,
                    ),
                )
                if was_created:
                    logger.info(
                        "UserLifecycleRegistry: created entry for user_uuid=%s (%s)",
                        user_uuid, email or phone,
                    )
                else:
                    logger.debug(
                        "UserLifecycleRegistry: row already exists for user_uuid=%s "
                        "(concurrent task or retry — no-op)",
                        user_uuid,
                    )
            except Exception as race_exc:
                # Unique constraint violation — another Celery worker inserted first.
                # This is expected and safe to ignore; the row exists.
                from django.db import IntegrityError as _IE
                if isinstance(race_exc, _IE):
                    logger.info(
                        "UserLifecycleRegistry: IntegrityError on user_uuid=%s "
                        "— concurrent insert, row already exists. Skipping.",
                        user_uuid,
                    )
                else:
                    raise


        elif action == "soft_deleted":
            updated = UserLifecycleRegistry.objects.filter(user_uuid=uid).update(
                status=UserLifecycleRegistry.STATUS_SOFT_DELETED,
                soft_deleted_at=now,
            )
            if updated == 0:
                logger.warning(
                    "UserLifecycleRegistry: no row for soft_deleted user_uuid=%s",
                    user_uuid,
                )

        elif action == "hard_deleted":
            updated = UserLifecycleRegistry.objects.filter(user_uuid=uid).update(
                status=UserLifecycleRegistry.STATUS_HARD_DELETED,
                hard_deleted_at=now,
            )
            if updated == 0:
                logger.warning(
                    "UserLifecycleRegistry: no row for hard_deleted user_uuid=%s",
                    user_uuid,
                )

        elif action == "restored":
            UserLifecycleRegistry.objects.filter(user_uuid=uid).update(
                status=UserLifecycleRegistry.STATUS_ACTIVE,
                restored_at=now,
                soft_deleted_at=None,
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


# ================================================================
# LOGIN COUNTER
# ================================================================

@shared_task(
    name="increment_lifecycle_login_counter",
    bind=True,
    max_retries=1,
    default_retry_delay=5,
    ignore_result=True,
)
def increment_lifecycle_login_counter(self, user_uuid: str, login_at=None):
    """
    Atomically increment ``total_logins`` and update ``last_login_at``
    in ``UserLifecycleRegistry`` for the given ``user_uuid``.

    Called from the login service after a successful authentication,
    wrapped in ``transaction.on_commit`` so it never blocks the response.

    Args:
        user_uuid (str): The UnifiedUser PK as a string.
        login_at  (str | None): ISO timestamp.  Defaults to now.
    """
    from django.db.models import F
    from django.utils import timezone
    from apps.common.models import UserLifecycleRegistry
    import uuid

    try:
        uid  = uuid.UUID(str(user_uuid))
        when = timezone.now() if login_at is None else login_at

        UserLifecycleRegistry.objects.filter(user_uuid=uid).update(
            total_logins=F("total_logins") + 1,
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
