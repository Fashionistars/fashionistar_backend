# apps/analytics/services/sentry_service.py
"""
Sentry error tracking integration helper for the analytics domain.

Wraps the optional sentry_sdk to capture exceptions, messages, and performance
transactions for analytics workflows, tasks, and API endpoints. If sentry_sdk is
not installed, calls degrade to no-ops so the rest of the analytics stack is
not affected.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

try:
    import sentry_sdk
    from sentry_sdk import capture_exception, capture_message, set_context, set_tag
    SENTRY_AVAILABLE = True
except ImportError:  # pragma: no cover
    sentry_sdk = None
    capture_exception = capture_message = set_context = set_tag = None  # type: ignore
    SENTRY_AVAILABLE = False

logger = logging.getLogger(__name__)


class AnalyticsSentryService:
    """Analytics-specific Sentry integration helper."""

    @staticmethod
    def is_available() -> bool:
        return SENTRY_AVAILABLE

    @staticmethod
    def capture_exception(
        exception: Exception,
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Capture an exception in Sentry with optional context and tags."""
        if not SENTRY_AVAILABLE:
            logger.debug("[AnalyticsSentryService] Sentry unavailable; exception not captured.")
            return None
        try:
            if tags:
                for key, value in tags.items():
                    set_tag(key, value)
            if context:
                for key, value in context.items():
                    set_context(key, value)
            return capture_exception(exception)
        except Exception as exc:
            logger.warning("[AnalyticsSentryService] capture_exception failed: %s", exc)
            return None

    @staticmethod
    def capture_message(
        message: str,
        level: str = "info",
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Capture a message in Sentry with optional context and tags."""
        if not SENTRY_AVAILABLE:
            logger.debug("[AnalyticsSentryService] Sentry unavailable; message not captured.")
            return None
        try:
            if tags:
                for key, value in tags.items():
                    set_tag(key, value)
            if context:
                for key, value in context.items():
                    set_context(key, value)
            return capture_message(message, level=level)
        except Exception as exc:
            logger.warning("[AnalyticsSentryService] capture_message failed: %s", exc)
            return None

    @staticmethod
    def set_tags(tags: Dict[str, str]) -> None:
        """Set global tags for the current Sentry scope."""
        if not SENTRY_AVAILABLE:
            return
        try:
            for key, value in tags.items():
                set_tag(key, value)
        except Exception as exc:
            logger.warning("[AnalyticsSentryService] set_tags failed: %s", exc)


def init_sentry() -> bool:
    """Initialize Sentry SDK if DSN is configured and sentry_sdk is installed."""
    from django.conf import settings

    if not SENTRY_AVAILABLE:
        logger.info("[AnalyticsSentryService] sentry_sdk not installed; skipping init.")
        return False

    dsn = getattr(settings, "SENTRY_DSN", None)
    environment = getattr(settings, "ENVIRONMENT", "development")
    release = getattr(settings, "RELEASE_VERSION", "unknown")

    if not dsn:
        logger.info("[AnalyticsSentryService] SENTRY_DSN not configured; skipping init.")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.1),
            profiles_sample_rate=getattr(settings, "SENTRY_PROFILES_SAMPLE_RATE", 0.05),
        )
        logger.info("[AnalyticsSentryService] Sentry initialized for environment=%s", environment)
        return True
    except Exception as exc:
        logger.warning("[AnalyticsSentryService] Sentry init failed: %s", exc)
        return False
