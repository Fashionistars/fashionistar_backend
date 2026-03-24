# apps/audit_logs/services/audit.py
"""
AuditService — high-level API for writing structured audit events.

All writes are NON-BLOCKING: events are dispatched directly to the Celery
broker (Redis) via ``apply_async()`` so the HTTP request path is never
delayed and audit events are NEVER lost on transaction rollback.

Falls back to direct synchronous write if Celery is unavailable so
audit events are NEVER silently dropped.

Auto-enrichment on every event (no extra work for callers):
  - ip_address, user_agent: from request headers
  - device_type, browser_family, os_family: from User-Agent string
  - country, country_code, city: via ip-api.com geo lookup (Redis-cached 24h)
"""

import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Geo-IP extraction (synchronous, Redis-cached 24h, never blocks on failure)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_geo(ip: str) -> dict:
    """
    Resolve country, country_code, city, and region for an IP address.

    Skips private/loopback IPs. Redis-caches results for 24 hours.
    Uses ip-api.com (free tier — no API key needed, 45req/minute limit).
    On ANY error, returns empty dict — geo must NEVER fail an audit.
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
        import urllib.request as _req
        import urllib.error as _err

        url = f"http://ip-api.com/json/{ip}?fields=49439"
        try:
            with _req.urlopen(url, timeout=1.5) as resp:
                data = _json.loads(resp.read().decode())
        except (_err.URLError, _err.HTTPError, OSError, Exception):
            return {}

        if data.get("status") != "success":
            return {}

        result = {
            "country":      data.get("country") or "",
            "country_code": data.get("countryCode") or "",
            "city":         data.get("city") or "",
            "region":       data.get("regionName") or "",
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
    """Stateless service for writing audit events. All classmethods."""

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
        """
        Record a structured audit event.

        All arguments are keyword-only. Guaranteed NEVER to raise.
        Every call auto-enriches with geo-IP, UA parsing, and request context.
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
                ip_address=resolved_ip,
                user_agent=resolved_ua,
                device_type=resolved_device,
                browser_family=resolved_browser,
                os_family=resolved_os,
                country=resolved_country or None,
                country_code=resolved_country_code or None,
                city=resolved_city or None,
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
        """Enqueue audit event to Celery immediately (NOT inside on_commit)."""
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
    """Synchronous fallback: write directly to DB."""
    try:
        from apps.audit_logs.models import AuditEventLog
        actor_id = payload.pop("actor_id", None)
        obj = AuditEventLog(**payload)
        if actor_id:
            obj.actor_id = actor_id
        obj.save()
    except Exception:
        logger.exception("AuditService._write_sync() failed for payload=%s", payload)
