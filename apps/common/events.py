# apps/common/events.py
"""
EventBus — lightweight in-process event system.

Replaces all Django signals as mandated by the FASHIONISTAR
backend architecture (AGENT_PLAN §1.1, BACKEND_ARCHITECTURE
§6.5). Provides a clean publish/subscribe pattern with:

    - Named events (string keys)
    - Synchronous handler dispatch
    - Thread-safe handler registry
    - Per-event and global subscriber lists
    - ``transaction.on_commit()`` integration for DB-safe
      event emission (use ``emit_on_commit()`` when events
      should fire AFTER the current transaction commits)

Usage::

    # Import the singleton
    from apps.common.events import event_bus

    # Subscribe
    def on_user_registered(user_id, email, **kwargs):
        send_welcome_email.delay(user_id=user_id)

    event_bus.subscribe('user.registered', on_user_registered)

    # Emit
    event_bus.emit('user.registered', user_id=str(u.pk), email=u.email)

    # Emit safely after DB transaction commits
    event_bus.emit_on_commit('order.placed', order_id=str(o.pk))

Architecture Notes:
    - Handlers are called synchronously in subscription order
    - Exceptions in one handler are caught and logged but
      do NOT prevent subsequent handlers from firing
    - Use Celery tasks inside handlers for actual async work
    - This is an in-process bus, not a message broker —
      for cross-process events use Celery/Redis pub/sub
"""

import asyncio
import logging
import threading
from collections import defaultdict
from typing import Any, Callable

from django.db import transaction

logger = logging.getLogger('application')


class EventBus:
    """
    Thread-safe synchronous in-process event bus.

    Attributes:
        _handlers (defaultdict[str, list[Callable]]): Maps
            event names to their registered handler callables.
        _lock (threading.Lock): Guards handler registry
            mutations to prevent race conditions in multi-
            threaded WSGI servers.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = (
            defaultdict(list)
        )
        self._lock = threading.Lock()

    def subscribe(
        self,
        event_name: str,
        handler: Callable,
    ) -> None:
        """
        Register a handler for a named event.

        The handler will be called every time ``emit()`` is
        invoked with the corresponding ``event_name``.

        Args:
            event_name (str): Dot-separated event identifier,
                e.g. ``'user.registered'``, ``'order.placed'``.
            handler (Callable): Any callable that accepts the
                keyword arguments passed to ``emit()``.

        Example::

            event_bus.subscribe('user.registered', my_handler)
        """
        with self._lock:
            if handler not in self._handlers[event_name]:
                self._handlers[event_name].append(handler)
                logger.debug(
                    "EventBus: subscribed %s to '%s'",
                    handler.__name__,
                    event_name,
                )

    def unsubscribe(
        self,
        event_name: str,
        handler: Callable,
    ) -> None:
        """
        Remove a previously registered handler.

        Silently ignores attempts to unsubscribe handlers
        that were never registered.

        Args:
            event_name (str): The event to unsubscribe from.
            handler (Callable): The handler to remove.
        """
        with self._lock:
            handlers = self._handlers.get(event_name, [])
            if handler in handlers:
                handlers.remove(handler)
                logger.debug(
                    "EventBus: unsubscribed %s from '%s'",
                    handler.__name__,
                    event_name,
                )

    def emit(self, event_name: str, **payload: Any) -> int:
        """
        Fire-and-forget: dispatch all handlers in a daemon background thread.

        PERFORMANCE UPGRADE:
            The previous implementation called handlers synchronously in the
            request thread, meaning a slow event handler (e.g. one that does
            I/O) would delay the HTTP response. This version returns in
            microseconds regardless of handler count or handler duration.

        Behaviour:
            • Handlers still receive all payload kwargs.
            • Exceptions in any handler are caught and logged.
            • Subscribers are snapshot at emit() call time (thread-safe).
            • The daemon thread is reaped when the process exits.

        Args:
            event_name (str): The event to emit.
            **payload: Keyword arguments forwarded to each handler.

        Returns:
            int: Number of handlers scheduled (not necessarily completed yet).
        """
        with self._lock:
            handlers = list(self._handlers.get(event_name, []))

        if not handlers:
            logger.debug("EventBus: no handlers for '%s'", event_name)
            return 0

        def _dispatch():
            success = 0
            for handler in handlers:
                try:
                    handler(**payload)
                    success += 1
                except Exception:
                    logger.exception(
                        "EventBus: handler %s raised for event '%s'",
                        getattr(handler, '__name__', repr(handler)),
                        event_name,
                    )
            logger.debug(
                "EventBus: emitted '%s' to %d/%d handler(s) [background]",
                event_name, success, len(handlers),
            )

        t = threading.Thread(target=_dispatch, daemon=True,
                             name=f"eventbus-{event_name}")
        t.start()
        return len(handlers)

    async def emit_async(self, event_name: str, **payload: Any) -> int:
        """
        Async-native emit for use inside async views / middleware.

        Dispatches handlers in a thread pool via ``asyncio.to_thread`` so
        the event loop is never blocked and no daemon thread is created
        outside the pool's control.

        Returns:
            int: Number of handlers scheduled.
        """
        with self._lock:
            handlers = list(self._handlers.get(event_name, []))

        if not handlers:
            return 0

        async def _run_handler(h):
            try:
                await asyncio.to_thread(h, **payload)
            except Exception:
                logger.exception(
                    "EventBus async: handler %s raised for event '%s'",
                    getattr(h, '__name__', repr(h)),
                    event_name,
                )

        import asyncio as _asyncio
        await _asyncio.gather(*[_run_handler(h) for h in handlers],
                              return_exceptions=False)
        return len(handlers)


    def emit_on_commit(
        self,
        event_name: str,
        **payload: Any,
    ) -> None:
        """
        Emit an event AFTER the current DB transaction commits.

        Uses ``transaction.on_commit()`` to guarantee that
        handlers only fire when the triggering database write
        has been durably committed. Use this for events that
        originate inside ``@transaction.atomic`` blocks (e.g.
        order placement, payment capture).

        Args:
            event_name (str): The event to emit on commit.
            **payload: Keyword arguments forwarded to handlers.

        Example::

            with transaction.atomic():
                order = Order.objects.create(...)
                event_bus.emit_on_commit(
                    'order.placed',
                    order_id=str(order.pk),
                )
        """
        transaction.on_commit(
            lambda: self.emit(event_name, **payload)
        )

    def subscribers(self, event_name: str) -> list[Callable]:
        """
        Return a copy of the handlers list for an event.

        Useful for introspection and testing.

        Args:
            event_name (str): The event to inspect.

        Returns:
            list[Callable]: Registered handlers (copy).
        """
        with self._lock:
            return list(self._handlers.get(event_name, []))

    def clear(self, event_name: str | None = None) -> None:
        """
        Remove all handlers for one event or all events.

        Primarily intended for use in tests to reset state
        between test cases.

        Args:
            event_name (str | None): If provided, clears only
                that event's handlers. If ``None``, clears
                the entire registry.
        """
        with self._lock:
            if event_name:
                self._handlers.pop(event_name, None)
            else:
                self._handlers.clear()


# ─── Module-level singleton ───────────────────────────────────────
# Import this in all apps:
#   from apps.common.events import event_bus
event_bus = EventBus()
