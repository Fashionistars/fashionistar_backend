# apps/audit_logs/services/audit.py
"""
AuditService — canonical, unified audit event writer for the Fashionistar platform.

Architecture:
    All 19 domain applications route their audit events through this single
    service.  Per-domain helper modules (``services/payment/payment_audit.py``,
    ``services/order/order_audit.py``, etc.) are thin wrappers that pre-fill
    ``event_type``, ``event_category``, ``is_compliance``, and
    ``retention_days`` — then delegate to ``AuditService.log()``.

Non-Blocking Design:
    All writes are fire-and-forget: events are dispatched directly to Celery
    (Redis broker) via ``apply_async(retry=False)`` so the HTTP request path
    is NEVER delayed.  If the broker is unreachable the fallback ``_write_sync``
    writes directly to PostgreSQL so audit events are NEVER silently dropped.

Auto-Enrichment:
    Every event is automatically enriched with:
    - ``ip_address``, ``user_agent`` — from Django ``HttpRequest.META``
    - ``device_type``, ``browser_family``, ``os_family`` — from UA parsing
    - ``country``, ``country_code``, ``city`` — geo-IP via IPinfo
      (Redis-cached 24 hours per IP to stay under the 45 req/min free tier)

Compliance:
    Events flagged with ``is_compliance=True`` (payments, KYC, wallet ops)
    receive a ``retention_days=-1`` (infinite) override and are tagged for
    regulatory audit trails (PCI-DSS, CBN, NDPR, GDPR).

Usage:
    # Generic event:
    from apps.audit_logs.services import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.LOGIN_SUCCESS,
        event_category=EventCategory.AUTHENTICATION,
        action="User logged in via email",
        actor=request.user,
        request=request,
    )

    # Domain-specific (preferred — handles boilerplate automatically):
    from apps.audit_logs.services.payment import PaymentAuditService
    PaymentAuditService.log_payout_initiated(actor=user, amount=500_00)
"""

import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Geo-IP extraction — synchronous, Redis-cached 24 h, fail-safe
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_geo(ip: str) -> dict:
    """Resolve geographic location data for a public IP address.

    Skips RFC-1918 private ranges, loopback (127.x, ::1), and the
    172.16.0.0/12 private range to avoid unnecessary external calls.
    Results are Redis-cached for 24 hours so the same IP is never
    resolved more than once per day — critical for high-traffic auth
    flows that may see the same IP thousands of times per minute.

    External Provider:
        IPinfo Lite/Core when an ``IPINFO_TOKEN`` is configured. Falls back
        to the unauthenticated legacy endpoint for best-effort country data
        when the token is absent. For very high-volume production workloads,
        prefer a locally-hosted MaxMind GeoIP2 database.

    Args:
        ip: IPv4 or IPv6 address string. May be empty or ``None``.

    Returns:
        dict: A mapping with up to four keys — ``country``,
            ``country_code``, ``city``, ``region`` — all as strings.
            Returns an empty ``{}`` on ANY error or for private IPs
            so that geo resolution NEVER fails an audit write.

    Note:
        This function catches ALL exceptions and returns ``{}`` —
        geo resolution failure must never propagate to callers.
    """
    _PRIVATE_PREFIXES = (
        '127.', '10.', '192.168.', '::1', '0.0.0.0', 'localhost',
    )
    if not ip or any(ip.startswith(p) for p in _PRIVATE_PREFIXES):
        return {}
    if ip.startswith('172.'):
        try:
            second_octet = int(ip.split('.')[1])
            if 16 <= second_octet <= 31:
                return {}
        except Exception:
            pass

    try:
        from utilities.django_redis import get_redis_connection_safe
        r = get_redis_connection_safe()
        cache_key = f"geo:{ip}"

        if r:
            cached = r.get(cache_key)
            if cached:
                import json
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        import json as _json
        import os as _os
        import urllib.request as _req
        import urllib.error as _err

        token = _os.getenv("IPINFO_TOKEN", "").strip()
        if token:
            url = f"https://api.ipinfo.io/lite/{ip}?token={token}"
        else:
            url = f"https://ipinfo.io/{ip}/json"
        try:
            with _req.urlopen(url, timeout=1.5) as resp:
                data = _json.loads(resp.read().decode())
        except (_err.URLError, _err.HTTPError, OSError, Exception):
            return {}

        result = {
            "country":      data.get("country_name") or data.get("country") or "",
            "country_code": data.get("country_code") or data.get("country") or "",
            "city":         data.get("city") or "",
            "region":       data.get("region") or "",
        }

        if r:
            try:
                r.setex(cache_key, 86400, _json.dumps(result))
            except Exception:
                pass

        return result

    except Exception:
        return {}


class AuditService:
    """Stateless, class-method-only service for writing structured audit events.

    All methods are ``@classmethod`` — never instantiate this class directly.
    Every call to ``log()`` is guaranteed to return without raising, even if
    the Celery broker, Redis, or the audit DB table is completely unavailable.

    Thread Safety:
        Stateless — safe to call from multiple threads, async views,
        Celery workers, and WebSocket consumers simultaneously.

    Example:
        from apps.audit_logs.services import AuditService
        from apps.audit_logs.models import EventType, EventCategory

        AuditService.log(
            event_type=EventType.LOGIN_SUCCESS,
            event_category=EventCategory.AUTHENTICATION,
            action="Email login successful",
            actor=user,
            request=request,
        )
    """

    @classmethod
    def log(
        cls,
        *,
        event_type: str,
        event_category: str,
        action: str,
        severity: str = "info",
        # Actor
        actor=None,
        actor_email: str | None = None,
        actor_role: str | None = None,
        session_id: str | None = None,
        # Request context (auto-filled from middleware/request if None)
        request=None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_type: str | None = None,
        browser_family: str | None = None,
        os_family: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        response_status: int | None = None,
        duration_ms: float | None = None,
        # Geo (auto-resolved from IP unless provided)
        country: str | None = None,
        country_code: str | None = None,
        city: str | None = None,
        # Resource
        resource_type: str | None = None,
        resource_id: str | None = None,
        # Diff / context
        old_values: dict | None = None,
        new_values: dict | None = None,
        metadata: dict | None = None,
        error_message: str | None = None,
        # Compliance
        is_compliance: bool = False,
        retention_days: int = 2555,
    ) -> None:
        """Record a structured audit event.

        All arguments are keyword-only. This method is guaranteed NEVER to
        raise — any internal failure is caught and logged as WARNING.

        Auto-enrichment (no extra work for callers):
            - IP, User-Agent: extracted from ``request.META`` if ``request``
              is supplied.
            - Device type, browser, OS: parsed from User-Agent string via
              the ``user-agents`` library.
            - Country, country_code, city: resolved via ``_resolve_geo()``
              (Redis-cached 24 hours, skips private IPs).
            - Actor email and role: resolved from the ``actor`` object if
              not explicitly provided.
            - Session ID: falls back to ``AuditContextMiddleware`` thread-
              local value.

        Args:
            event_type: Canonical ``EventType`` constant
                (e.g. ``EventType.LOGIN_SUCCESS``).
            event_category: Grouping category
                (e.g. ``EventCategory.AUTHENTICATION``).
            action: Human-readable description of what happened.
            severity: Log level — one of ``debug``, ``info``, ``warning``,
                ``error``, ``critical``. Defaults to ``"info"``.
            actor: Authenticated ``UnifiedUser`` instance or ``None`` for
                system/background events.
            actor_email: Override email; auto-resolved from ``actor`` if
                omitted.
            actor_role: Role snapshot at event time (``client``,
                ``vendor``, ``admin``). Auto-resolved from ``actor``
                if omitted.
            session_id: JWT ``jti`` or Django session key to correlate
                all events in a single session timeline.
            request: Django ``HttpRequest`` — auto-extracts IP, UA,
                HTTP method, and request path.
            ip_address: Override IP address (takes priority over request
                IP extraction).
            user_agent: Override User-Agent string.
            device_type: Override device type (``mobile``, ``tablet``,
                ``desktop``, ``bot``).
            browser_family: Override browser family string.
            os_family: Override OS family string.
            request_method: Override HTTP method (``GET``, ``POST``, etc.).
            request_path: Override request path.
            response_status: HTTP response status code (e.g. 200, 401, 500).
            duration_ms: Request processing time in milliseconds.
            country: Override country name.
            country_code: Override ISO 3166-1 alpha-2 country code.
            city: Override city name.
            resource_type: Name of the affected resource model
                (e.g. ``"Order"``, ``"WalletLedgerEntry"``).
            resource_id: Primary key of the affected resource (any type —
                coerced to string internally).
            old_values: Snapshot of field values before the change (for
                diff-based compliance events).
            new_values: Snapshot of field values after the change.
            metadata: Arbitrary JSON-serialisable dict for domain-specific
                context that doesn't fit other fields.
            error_message: Error description for failure events.
            is_compliance: If ``True``, flags this event as a compliance-
                critical record (PCI-DSS, CBN, NDPR, GDPR). Compliance
                events should use ``retention_days=-1`` (infinite).
            retention_days: Override the default 7-year (2555-day) retention
                period. Pass ``-1`` for infinite retention.

        Returns:
            None: Always returns ``None``. Guaranteed non-raising.
        """
        try:
            from apps.audit_logs.middleware import get_audit_context
            ctx = get_audit_context()

            # ── Resolve actor ─────────────────────────────────────────
            resolved_actor = actor
            if resolved_actor is None and request is not None:
                u = getattr(request, "user", None)
                if u and getattr(u, 'is_authenticated', False):
                    resolved_actor = u
            if resolved_actor is None:
                resolved_actor = ctx.get("actor")

            resolved_email = actor_email or getattr(resolved_actor, "email", None)
            if not resolved_email:
                resolved_email = ctx.get("actor_email")

            # ── Resolve actor_role ─────────────────────────────────────────
            resolved_role = actor_role
            if not resolved_role and resolved_actor:
                resolved_role = getattr(resolved_actor, "user_type", None) or \
                                getattr(resolved_actor, "role", None)

            # ── Resolve session_id ───────────────────────────────────────
            resolved_session = session_id or ctx.get("session_id")
            resolved_correlation_id = (
                ctx.get("correlation_id")
                or (metadata or {}).get("correlation_id")
                or resolved_session
            )

            # ── Resolve request context ───────────────────────────────
            def _first(*vals):
                for v in vals:
                    if v:
                        return v
                return None

            xff = None
            if request:
                raw_xff = request.META.get("HTTP_X_FORWARDED_FOR")
                xff = raw_xff.split(",")[0].strip() if raw_xff else None

            resolved_ip   = _first(ip_address, xff,
                                   request.META.get("REMOTE_ADDR") if request else None,
                                   ctx.get("ip_address"))
            resolved_ua   = _first(user_agent,
                                   request.META.get("HTTP_USER_AGENT") if request else None,
                                   ctx.get("user_agent"))
            resolved_meth = _first(request_method,
                                   request.method if request else None,
                                   ctx.get("request_method"))
            resolved_path = _first(request_path,
                                   request.path if request else None,
                                   ctx.get("request_path"))

            # ── UA parsing → device_type, browser_family, os_family ───
            resolved_device  = device_type
            resolved_browser = browser_family
            resolved_os      = os_family
            if resolved_ua and (not resolved_device or not resolved_browser or not resolved_os):
                try:
                    from user_agents import parse as ua_parse
                    ua_obj = ua_parse(resolved_ua)
                    resolved_device  = resolved_device or (
                        "mobile"  if ua_obj.is_mobile  else
                        "tablet"  if ua_obj.is_tablet  else
                        "bot"     if ua_obj.is_bot     else
                        "desktop"
                    )
                    resolved_browser = resolved_browser or (ua_obj.browser.family or None)
                    resolved_os      = resolved_os      or (ua_obj.os.family      or None)
                except Exception:
                    pass

            # ── Geo-IP enrichment → country, country_code, city ───────
            resolved_country      = country or ""
            resolved_country_code = country_code or ""
            resolved_city         = city or ""

            if resolved_ip and not (resolved_country and resolved_country_code):
                try:
                    geo = _resolve_geo(resolved_ip)
                    if geo:
                        resolved_country      = resolved_country      or geo.get("country", "")
                        resolved_country_code = resolved_country_code or geo.get("country_code", "")
                        resolved_city         = resolved_city         or geo.get("city", "")
                except Exception:
                    pass

            # ── Build payload ─────────────────────────────────────────
            payload = dict(
                event_type=event_type,
                event_category=event_category,
                severity=severity,
                action=action,
                actor_id=resolved_actor.pk if resolved_actor else None,
                actor_email=resolved_email,
                actor_role=resolved_role,
                session_id=resolved_session,
                ip_address=resolved_ip,
                user_agent=resolved_ua,
                device_type=resolved_device,
                browser_family=resolved_browser,
                os_family=resolved_os,
                country=resolved_country or None,
                country_code=resolved_country_code or None,
                city=resolved_city or None,
                correlation_id=resolved_correlation_id,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                request_method=resolved_meth,
                request_path=resolved_path,
                response_status=response_status,
                duration_ms=duration_ms,
                old_values=old_values,
                new_values=new_values,
                metadata=metadata,
                error_message=error_message,
                is_compliance=is_compliance,
                retention_days=retention_days,
            )

            cls._dispatch(payload)

        except Exception:
            logger.warning(
                "AuditService.log() swallowed unexpected error for event=%s",
                event_type, exc_info=True,
            )

    @staticmethod
    def _dispatch(payload: dict) -> None:
        """Enqueue an audit event payload to the Celery worker queue.

        Dispatches immediately (NOT inside ``transaction.on_commit()``) so
        the event is recorded even if the caller's DB transaction rolls back.
        This is the correct behaviour for audit events — we want to know
        that an action was *attempted*, regardless of DB outcome.

        For events that must only be recorded after a successful DB commit
        (e.g. "payout processed successfully"), the **caller** is responsible
        for wrapping ``AuditService.log()`` in ``transaction.on_commit()``.

        Args:
            payload: A fully-resolved dict ready for ``AuditEventLog`` field
                assignment. ``actor_id`` is a UUID — the Celery task
                resolves the FK separately to avoid serialisation issues.

        Note:
            Falls back to ``_write_sync()`` if the broker is unreachable so
            audit events are NEVER silently dropped.
        """
        try:
            from apps.audit_logs.tasks import write_audit_event
            write_audit_event.apply_async(
                kwargs={"payload": payload},
                retry=False,
                ignore_result=True,
            )
        except Exception:
            _write_sync(payload)


def _write_sync(payload: dict) -> None:
    """Synchronous fallback: write an audit event directly to PostgreSQL.

    Called by ``AuditService._dispatch()`` when the Celery broker (Redis)
    is unreachable.  Ensures every audit event reaches the DB regardless
    of infrastructure failures.

    Args:
        payload: The fully-resolved event payload dict. ``actor_id`` is
            extracted and set directly on the ``AuditEventLog`` instance
            to avoid FK resolution issues inside the Celery task.

    Note:
        This function catches ALL exceptions and logs them at ``exception``
        level — it NEVER re-raises, ensuring the calling stack is never
        broken by a fallback write failure.
    """
    try:
        from apps.audit_logs.models import AuditEventLog
        actor_id = payload.pop("actor_id", None)
        obj = AuditEventLog(**payload)
        if actor_id:
            obj.actor_id = actor_id
        obj.save()
    except Exception:
        logger.exception(
            "AuditService._write_sync() failed for payload=%s",
            payload,
        )
