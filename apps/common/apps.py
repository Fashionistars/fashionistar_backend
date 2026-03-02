"""
App configuration for the common app.

This module defines the configuration for the 'common' Django app,
which provides shared utilities, models, and permissions across the
project.

The ``ready()`` hook:
  1. Connects the analytics signal handlers from ``apps.common.signals``.
  2. Starts the async logging QueueListener — all log records emitted from
     the event loop are enqueued instantly (nanoseconds) and flushed to the
     actual file/console handlers in a dedicated background thread, ensuring
     file I/O NEVER blocks the ASGI event loop or Uvicorn worker threads.
"""

import atexit
import logging
import logging.handlers
import queue

from django.apps import AppConfig


class CommonConfig(AppConfig):
    """
    Configuration class for the common app.

    ``ready()`` imports ``apps.common.signals`` so that the
    ``post_save`` / ``post_delete`` handlers are connected as
    soon as the Django registry is fully loaded. Without this
    the signal receivers would never be registered.

    It also wires the async logging pipeline:
      QueueHandler  →  (in-process queue)  →  QueueListener  →  real handlers

    This pattern is recommended in the Python logging cookbook for
    applications that perform async I/O (asyncio, Twisted) where blocking
    file writes on the event loop thread would hurt throughput.

    Attributes:
        default_auto_field (str): Default auto field type.
        name (str): App name as used in Django settings.
        verbose_name (str): Human-readable name.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.common'
    verbose_name = 'Common Utilities'

    def ready(self):
        """
        Wire signal receivers and start the async logging queue listener.
        """
        # ── 1. Connect analytics signal receivers ─────────────────────────────
        import apps.common.signals  # noqa: F401

        # ── 2. Start async logging pipeline ──────────────────────────────────
        # Build a SimpleQueue and attach it to the root logger via a
        # QueueHandler. All existing handlers are moved to the QueueListener
        # so they run in the background thread — never on the event loop.
        _setup_async_logging()


def _setup_async_logging() -> None:
    """
    Redirect all existing logging handlers through a QueueListener.

    Strategy:
      • Walk every logger in the manager's hierarchy.
      • Collect all non-QueueHandler handlers.
      • Replace them with a single QueueHandler feeding a SimpleQueue.
      • Start a QueueListener that drains the queue in a background thread.
      • Register listener.stop() via atexit to flush on process exit.

    This is idempotent: if the QueueListener is already running (e.g. in
    Django's autoreloader worker process), it skips re-wiring.
    """
    root_logger = logging.getLogger()

    # Guard: already wired (autoreloader calls ready() twice)
    if any(isinstance(h, logging.handlers.QueueHandler)
           for h in root_logger.handlers):
        return

    log_queue: queue.SimpleQueue = queue.SimpleQueue()

    # Collect the real handlers from root + all child loggers
    real_handlers: list[logging.Handler] = []
    seen_ids: set[int] = set()

    all_loggers = [root_logger] + [
        logging.getLogger(name)
        for name in logging.Logger.manager.loggerDict
        if isinstance(logging.Logger.manager.loggerDict[name], logging.Logger)
    ]

    for lg in all_loggers:
        for h in list(lg.handlers):
            if isinstance(h, logging.handlers.QueueHandler):
                continue  # already async
            hid = id(h)
            if hid not in seen_ids:
                real_handlers.append(h)
                seen_ids.add(hid)
            # Remove from the logger — the listener will call them instead
            lg.removeHandler(h)

    if not real_handlers:
        # Fallback: keep a StreamHandler so we don't lose output entirely
        real_handlers = [logging.StreamHandler()]

    # Attach a single QueueHandler to root — all child loggers propagate here
    queue_handler = logging.handlers.QueueHandler(log_queue)
    root_logger.addHandler(queue_handler)

    # Start the listener (runs in a daemon thread)
    listener = logging.handlers.QueueListener(
        log_queue,
        *real_handlers,
        respect_handler_level=True,
    )
    listener.start()

    # Stop on process exit (flushes any queued records)
    atexit.register(listener.stop)
