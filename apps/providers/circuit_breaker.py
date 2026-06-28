# apps/providers/circuit_breaker.py
"""
Circuit Breaker for the Fashionistar Provider Registry.

Implements a three-state Finite State Machine (FSM) that protects the platform
from cascade failures when an external provider (payment gateway, KYC service,
SMS operator) experiences degraded or failed availability.

States:
    CLOSED    — Normal operation.  All provider calls pass through.
    OPEN      — Provider is failing.  Calls are blocked to prevent load amplification.
                An admin alert email is sent once per open event.
    HALF_OPEN — Recovery probe.  One call is permitted to test if the provider
                has recovered.  Success → CLOSED; failure → OPEN again.

Failure Threshold:
    ``FAILURE_THRESHOLD = 5`` consecutive errors → transitions to OPEN.

Recovery Timeout:
    After the circuit opens, calls are blocked until a successful probe call
    causes the ``record_success()`` method on the provider config to close it.

Admin Alert:
    - Sent to the first active superuser's email on circuit-open.
    - De-duplicated via Redis (``ALERT_DEDUP_TTL = 3600 s``) to prevent
      admin inbox flooding on sustained provider failures.
    - Alert email includes a direct link to the Django Admin provider config page.

Usage — Decorator (recommended for provider driver methods):

    from apps.providers.circuit_breaker import circuit_breaker

    @circuit_breaker("kyc")
    def call_kyc_provider(config, bvn_hash, last4): ...

Usage — Context Manager (for inline dispatch, e.g. in OlivePayClient):

    from apps.providers.circuit_breaker import CircuitBreaker

    _breaker = CircuitBreaker(provider_key="olive_pay", failure_threshold=5)

    def _call():
        return client.post(...)

    result = _breaker.call(_call)

Usage — ``.call()`` method (for passing a callable, e.g. in OlivePayClient):

    _breaker = CircuitBreaker("olive_pay", failure_threshold=5)
    response = _breaker.call(lambda: api_client.post("/payments/initialize", ...))
"""
from __future__ import annotations

import functools
import logging
from datetime import datetime, timezone
from typing import Callable

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("application")

# ── Module-Level Constants ─────────────────────────────────────────────────────
FAILURE_THRESHOLD = 5                # Failures before circuit OPENS
RECOVERY_TIMEOUT_SECONDS = 60        # Seconds before HALF_OPEN probe allowed
ALERT_DEDUP_TTL = 3600               # 1 hour — suppress repeated admin alerts


class CircuitOpenError(Exception):
    """Raised when a provider call is attempted while the circuit is OPEN.

    Attributes:
        provider_name: The name of the provider whose circuit is open.
    """

    def __init__(self, provider_name: str = "") -> None:
        self.provider_name = provider_name
        super().__init__(
            f"Circuit breaker is OPEN for provider: {provider_name!r}. "
            "Provider is degraded — call blocked to prevent cascade failures."
        )


# ── Admin Alert Helper ─────────────────────────────────────────────────────────

def _send_circuit_open_alert(
    provider_name: str,
    failure_count: int,
    error: Exception,
) -> None:
    """Send a one-time superuser email alert when a provider circuit opens.

    Uses Redis-based de-duplication to ensure only one alert is delivered per
    open event, even if many requests fail simultaneously.

    Args:
        provider_name: Human-readable name of the failing provider
                       (e.g. ``"kyc"``, ``"olive_pay"``).
        failure_count: Number of consecutive failures that triggered the open.
        error: The last exception that caused the circuit to open.
    """
    dedup_key = f"circuit_alert_sent:{provider_name}"
    if cache.get(dedup_key):
        logger.debug(
            "Circuit breaker alert suppressed (de-dup) for provider=%s", provider_name
        )
        return

    try:
        from django.contrib.auth import get_user_model
        from django.core.mail import send_mail

        User = get_user_model()
        superuser = (
            User.objects.filter(is_superuser=True, is_active=True)
            .order_by("date_joined")
            .first()
        )
        if not superuser or not superuser.email:
            logger.error(
                "CircuitBreaker: cannot send alert — no active superuser email found."
            )
            return

        admin_url = (
            f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/admin/providers/"
        )

        subject = f"[FASHIONISTAR] ⚠️ Provider Circuit OPEN: {provider_name}"
        message = (
            f"The Fashionistar platform circuit breaker has OPENED for provider: "
            f"{provider_name!r}\n\n"
            f"Failure count : {failure_count}\n"
            f"Last error    : {error}\n"
            f"Timestamp     : {datetime.now(tz=timezone.utc).isoformat()}\n\n"
            f"ACTION REQUIRED:\n"
            f"  1. Log in to the admin panel: {admin_url}\n"
            f"  2. Navigate to the failing provider configuration.\n"
            f"  3. Switch to a healthy backup provider and SAVE.\n"
            f"  4. The circuit will automatically close on the next successful call.\n\n"
            f"This is an automated alert from the Fashionistar Provider Registry."
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "noreply@fashionistar.net"
            ),
            recipient_list=[superuser.email],
            fail_silently=True,
        )

        # Mark alert as sent — suppress duplicates for ALERT_DEDUP_TTL seconds
        cache.set(dedup_key, True, ALERT_DEDUP_TTL)
        logger.warning(
            "CircuitBreaker: OPEN alert sent to %s for provider=%s",
            superuser.email,
            provider_name,
        )
    except Exception as exc:
        logger.error("CircuitBreaker: failed to send admin alert: %s", exc)


# ── Circuit Breaker Core ───────────────────────────────────────────────────────

class CircuitBreaker:
    """Three-state circuit breaker for a named external provider.

    Protects Fashionistar from cascade failures when a provider degrades.
    State (failure count, circuit state) is persisted in the ``ProviderConfig``
    DB model via ``record_failure()`` / ``record_success()`` so the state
    survives process restarts and is visible in the Django Admin.

    The ``provider_name`` (or ``provider_key``) is used for:
      - Log messages and alert de-duplication (Redis key prefix).
      - Dispatching to the correct config loader in ``_load_config()``.

    Supports three usage patterns:

    1. **Decorator**::

           @CircuitBreaker("kyc")
           def call_provider(config, ...): ...

    2. **Context manager**::

           cb = CircuitBreaker("sms")
           with cb:
               driver.send(to=phone, message=text)

    3. **``.call()`` method** (for lambdas / inline callables)::

           _breaker = CircuitBreaker("olive_pay", failure_threshold=5)
           result = _breaker.call(lambda: api_client.post("/payments/initialize"))

    Attributes:
        provider_name: Canonical provider key (e.g. ``"kyc"``, ``"sms"``,
                       ``"olive_pay"``).
        failure_threshold: Number of consecutive failures before opening.
        _last_error: The most recent exception recorded by ``_on_failure``.
    """

    def __init__(
        self,
        provider_name: str = "",
        *,
        provider_key: str = "",
        failure_threshold: int = FAILURE_THRESHOLD,
    ) -> None:
        """Initialise the circuit breaker for a named provider.

        Args:
            provider_name: Canonical provider name (positional, for decorator usage).
            provider_key: Alias for ``provider_name`` (keyword-only, for explicit usage).
                          If both are supplied, ``provider_key`` takes precedence.
            failure_threshold: Override the default failure threshold.
                               Defaults to module-level ``FAILURE_THRESHOLD = 5``.
        """
        self.provider_name: str = provider_key or provider_name
        self.failure_threshold: int = failure_threshold
        self._last_error: Exception | None = None

    # ── Context Manager Interface ──────────────────────────────────────────────

    def __enter__(self) -> "CircuitBreaker":
        """Enter the circuit breaker context.

        Returns:
            CircuitBreaker: Self reference (allows ``as cb`` pattern).
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit the circuit breaker context, recording success or failure.

        Args:
            exc_type: Exception class if an exception was raised, else ``None``.
            exc_val: Exception instance if raised, else ``None``.
            exc_tb: Traceback object if an exception was raised, else ``None``.

        Returns:
            bool: Always ``False`` — exceptions are never suppressed by this breaker.
        """
        if exc_type is None:
            self._on_success()
        else:
            self._on_failure(exc_val)
        return False  # Never suppress exceptions — let them propagate

    # ── Decorator Interface ────────────────────────────────────────────────────

    def __call__(self, func: Callable) -> Callable:
        """Wrap a function with circuit breaker protection.

        Args:
            func: The callable to protect.

        Returns:
            Callable: A wrapped version of ``func`` that records success/failure
                      with the circuit breaker on each invocation.
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return wrapper

    # ── .call() Convenience Method ─────────────────────────────────────────────

    def call(self, func: Callable):
        """Execute a callable with circuit breaker protection.

        Equivalent to using the breaker as a context manager, but suitable
        for one-off lambda or inline callable invocations.

        Args:
            func: A zero-argument callable to execute (e.g. ``lambda: api.post(...)``).

        Returns:
            Any: Return value of ``func()``.

        Raises:
            Exception: Re-raises any exception from ``func`` after recording the failure.
        """
        with self:
            return func()

    def record_success(self) -> None:
        """Public hook for providers that return failure objects instead of raising."""
        self._on_success()

    def record_failure(self, exc: Exception) -> None:
        """Public hook for providers that normalize errors into result objects."""
        self._on_failure(exc)

    # ── Internal State Transitions ─────────────────────────────────────────────

    def _on_success(self) -> None:
        """Record a successful provider call and close the circuit.

        Delegates to ``config.record_success()`` on the active provider config
        to reset the failure counter in the DB.  Errors here are swallowed and
        logged — a DB write failure must not mask the original success result.
        """
        try:
            config = self._load_config()
            if config and config.pk:
                config.record_success()
                logger.info(
                    "CircuitBreaker[%s]: SUCCESS — circuit closed.",
                    self.provider_name,
                )
        except Exception as exc:
            logger.error("CircuitBreaker._on_success DB error: %s", exc)

    def _on_failure(self, exc: Exception) -> None:
        """Record a failed provider call and open the circuit if threshold reached.

        Increments the failure counter on the active provider config via
        ``config.record_failure()``.  If the updated failure count meets or
        exceeds ``failure_threshold``, a superuser alert email is dispatched.

        Args:
            exc: The exception that caused the provider call to fail.
        """
        self._last_error = exc
        try:
            config = self._load_config()
            if config and config.pk:
                config.record_failure()
                config.refresh_from_db()  # Ensure we see the DB-updated count
                failure_count = config.failure_count

                logger.warning(
                    "CircuitBreaker[%s]: failure #%d — %s",
                    self.provider_name,
                    failure_count,
                    exc,
                )

                if failure_count >= self.failure_threshold:
                    logger.critical(
                        "CircuitBreaker[%s]: OPEN (failure_count=%d). Admin alert sending.",
                        self.provider_name,
                        failure_count,
                    )
                    _send_circuit_open_alert(self.provider_name, failure_count, exc)
        except Exception as db_exc:
            logger.error("CircuitBreaker._on_failure DB error: %s", db_exc)

    def _load_config(self):
        """Resolve the active provider config for this provider key.

        Dispatches to the appropriate cache loader based on the leading segment
        of ``provider_name`` (e.g. ``"kyc"`` → ``get_kyc_provider_config()``).

        Returns:
            ProviderConfig | None: The active config instance, or ``None`` if
                                   the provider key is unrecognised or the loader
                                   raises an exception.
        """
        try:
            from apps.providers.cache import (   # noqa: PLC0415
                get_email_provider_config,
                get_kyc_provider_config,
                get_sms_provider_config,
            )
            dispatch = {
                "kyc": get_kyc_provider_config,
                "email": get_email_provider_config,
                "sms": get_sms_provider_config,
            }
            loader = dispatch.get(self.provider_name.split(":")[0])
            if loader:
                return loader()
        except Exception as exc:
            logger.error("CircuitBreaker._load_config error: %s", exc)
        return None


# ── Convenience Decorator Factory ──────────────────────────────────────────────

def circuit_breaker(provider_name: str) -> Callable:
    """Return a circuit-breaker decorator for the named provider.

    This is a factory that creates a ``CircuitBreaker`` instance and wraps
    the decorated function so every call is protected.

    Args:
        provider_name: Canonical provider key (e.g. ``"kyc"``, ``"sms"``).

    Returns:
        Callable: A decorator that wraps functions with circuit breaker protection.

    Example::

        @circuit_breaker("kyc")
        def call_kyc_api(config, bvn_hash, last4): ...
    """
    def decorator(func: Callable) -> Callable:
        cb = CircuitBreaker(provider_name)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with cb:
                return func(*args, **kwargs)

        return wrapper
    return decorator


__all__ = [
    "CircuitBreaker",
    "CircuitOpenError",
    "FAILURE_THRESHOLD",
    "RECOVERY_TIMEOUT_SECONDS",
    "circuit_breaker",
]
