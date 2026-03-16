# apps/common/event_handlers.py
"""
Event Handlers — Common App

Subscribes handlers to events emitted by other apps via the EventBus
(apps.common.events).  This module is the ONLY place in apps.common that
contains event handling logic; it is deliberately kept separate from models.py,
tasks.py, and signals.py to give each layer a clear single responsibility.

Handlers are registered in CommonConfig.ready() to guarantee they are wired
exactly once, after all models have been loaded.

Architecture
------------
    Publisher           → Event name              → Handler here
    ────────────────────────────────────────────────────────────
    sync_service.py     → 'user.registered'       → on_user_registered
    (future)            → 'order.placed'           → (register in ready())
    (future)            → 'payment.captured'       → (register in ready())

Contract
--------
    * Handlers MUST NOT do synchronous I/O inside the handler itself.
      Dispatch to Celery tasks instead (fire-and-forget, non-blocking).
    * Each handler is called AFTER transaction.on_commit() resolves,
      guaranteeing the user row is in the database before the Celery
      worker tries to read it.
    * Handlers are idempotent: firing twice for the same user_uuid
      must not create duplicate records (use get_or_create / filter).

Integration Guide (for future apps)
------------------------------------
    # In your service:
    from apps.common.events import event_bus
    event_bus.emit_on_commit('user.registered',
        user_uuid=str(user.pk),
        email=user.email,
        phone=str(user.phone) if user.phone else None,
        member_id=user.member_id or '',
        role=user.role or '',
        auth_provider=user.auth_provider or 'email',
        country=user.country or None,
        state=user.state or None,
        city=user.city or None,
    )

    # In your handler:
    from apps.common.event_handlers import on_user_registered
    event_bus.subscribe('user.registered', on_user_registered)
"""

import logging

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# Handler: user.registered
# ════════════════════════════════════════════════════════════════

def on_user_registered(
    user_uuid: str,
    email: str | None = None,
    phone: str | None = None,
    member_id: str = '',
    role: str = '',
    auth_provider: str = 'email',
    country: str | None = None,
    state: str | None = None,
    city: str | None = None,
    **kwargs,  # forward-compatibility — future payload fields are silently ignored
) -> None:
    """
    Fire when a new UnifiedUser has been successfully created and committed.

    Emitted by:
        apps.authentication.services.registration.sync_service.register_sync()
        via event_bus.emit_on_commit('user.registered', ...)

    Action:
        Dispatches upsert_user_lifecycle_registry Celery task which writes a
        permanent, append-only lifecycle record for the new user.  If Celery /
        Redis is unavailable the fallback path creates the record synchronously
        via UserLifecycleRegistry.objects.get_or_create() — ensuring zero data
        loss even in degraded infrastructure.

    Idempotency:
        The Celery task uses get_or_create(user_uuid=...) so firing this handler
        twice for the same user is safe (second call is a no-op).

    Args:
        user_uuid:    str UUID of the created UnifiedUser.
        email:        User's email address (None for phone-only).
        phone:        User's phone in E.164 string (None for email-only).
        member_id:    Brand member ID (e.g. 'FASTAR000001').
        role:         RBAC role string ('client', 'vendor', 'admin', …).
        auth_provider: 'email' | 'phone' | 'google'.
        country/state/city: Geographic data captured at registration time.
        **kwargs:     Silently ignored; allows future payload expansion without
                      breaking existing handlers.
    """
    logger.debug(
        "EventBus: on_user_registered fired for user_uuid=%s", user_uuid
    )

    try:
        from apps.common.tasks import upsert_user_lifecycle_registry  # type: ignore

        upsert_user_lifecycle_registry.apply_async(
            kwargs=dict(
                user_uuid=user_uuid,
                action='created',
                email=email,
                phone=phone,
                member_id=member_id,
                role=role,
                auth_provider=auth_provider,
                country=country,
                state=state,
                city=city,
            ),
            retry=False,
            ignore_result=True,
        )
        logger.info(
            "EventBus: upsert_user_lifecycle_registry queued for user_uuid=%s",
            user_uuid,
        )

    except Exception:  # noqa: BLE001 — Celery / Redis unavailable
        logger.warning(
            "EventBus: Celery unavailable for on_user_registered(%s) — "
            "falling back to synchronous UserLifecycleRegistry.get_or_create()",
            user_uuid,
        )
        try:
            from apps.common.models import UserLifecycleRegistry  # type: ignore
            UserLifecycleRegistry.objects.get_or_create(
                user_uuid=user_uuid,
                defaults=dict(
                    email=email,
                    phone=phone,
                    member_id=member_id,
                    role=role,
                    auth_provider=auth_provider,
                    country=country,
                    state=state,
                    city=city,
                    status='active',
                ),
            )
            logger.info(
                "EventBus: sync fallback UserLifecycleRegistry created for %s",
                user_uuid,
            )
        except Exception as inner_exc:  # noqa: BLE001
            logger.error(
                "EventBus: BOTH Celery and sync fallback failed for "
                "on_user_registered(%s): %s",
                user_uuid,
                inner_exc,
            )
