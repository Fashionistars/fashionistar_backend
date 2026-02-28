# apps/common/middleware.py
"""
Production-grade Django WSGI middleware for the Fashionistar backend.

Middleware stack (register in this order in settings.py)::

    1. RequestIDMiddleware    — UUID4 per-request trace ID
    2. RequestTimingMiddleware  — logs method/path/status/duration
    3. SecurityAuditMiddleware  — full security audit trail with:
       IP, Device-ID, Session, User-Agent, role, URL, status

SecurityAuditMiddleware
-----------------------
Captures the full security audit trail of every HTTP interaction.

Each log line contains:
    - Timestamp (via logging formatter)
    - X-Request-ID (correlation across services)
    - Device ID (X-Device-ID header or UA+IP fingerprint)
    - Session key (first 16 chars, for cross-request tracing)
    - Client IP (X-Forwarded-For → REMOTE_ADDR)
    - HTTP method and full path
    - Response status code
    - Wall-clock duration in ms
    - User ID and role (or 'anonymous')
    - User-Agent string (first 300 chars)
    - Referrer URL

Log levels:
    INFO    — successful requests (2xx, 3xx)
    WARNING — authentication / permission failures (401, 403)
    ERROR   — server errors (5xx)

Registration (settings.py MIDDLEWARE list)::

    MIDDLEWARE = [
        'apps.common.middleware.RequestIDMiddleware',
        'apps.common.middleware.RequestTimingMiddleware',
        'apps.common.middleware.SecurityAuditMiddleware',
        ...
    ]
"""

import hashlib
import logging
import time
import uuid

logger = logging.getLogger('application')
security_logger = logging.getLogger('security')


# ================================================================
# 1. REQUEST ID INJECTION
# ================================================================

class RequestIDMiddleware:
    """
    Inject a unique UUID4 ``X-Request-ID`` into every
    request and response.

    The request ID is:
        - Read from the incoming ``X-Request-ID`` header
          if provided by a load balancer or API gateway
          (allows distributed tracing across services).
        - Generated fresh as a UUID4 if not present.
        - Stored on ``request.request_id`` for use in view
          code, serializers, and log formatters.
        - Written to the response ``X-Request-ID`` header
          so clients and proxies can correlate requests.

    Args:
        get_response: The next middleware or view callable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Honour upstream request ID (e.g. from nginx / ELB)
        request_id = (
            request.headers.get('X-Request-Id')
            or request.headers.get('X-Request-ID')
            or str(uuid.uuid4())
        )
        request.request_id = request_id

        response = self.get_response(request)

        # Propagate to client for distributed tracing
        response['X-Request-ID'] = request_id
        return response


# ================================================================
# 2. REQUEST TIMING
# ================================================================

class RequestTimingMiddleware:
    """
    Log method, path, status code, and wall-clock time (ms)
    for every HTTP request.

    Output format::

        [GET] /api/v2/auth/login/ → 200 in 34.7ms [req=<uuid>]

    Args:
        get_response: The next middleware or view callable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()

        response = self.get_response(request)

        duration_ms = (time.monotonic() - start) * 1000
        request_id = getattr(request, 'request_id', '-')

        logger.info(
            "[%s] %s → %d in %.1fms [req=%s]",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            request_id,
        )

        # Expose timing to clients (useful for devtools)
        response['X-Response-Time'] = f"{duration_ms:.1f}ms"
        return response


# ================================================================
# 3. SECURITY AUDIT MIDDLEWARE — helpers
# ================================================================

def _get_client_ip(request):
    """
    Extract the real client IP address.

    Checks ``X-Forwarded-For`` first (Nginx / load balancer /
    Cloudflare), then falls back to ``REMOTE_ADDR``.
    Only the leftmost IP in the XFF chain is used.

    Returns:
        str: Client IP address.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _get_device_id(request):
    """
    Extract or derive a stable device identifier.

    Priority:
    1. ``X-Device-ID`` header — explicitly sent by mobile apps /
       desktop clients / API integrations (most reliable).
    2. ``X-Fingerprint`` header — some SDKs send a pre-computed
       client fingerprint.
    3. SHA-256 of (User-Agent + IP) — stable across sessions
       for the same browser/IP pair. Prefixed with ``fp:`` so
       log consumers know it is derived, not device-supplied.

    The value is also stored on ``request.device_id`` so views
    and serializers can reference it without re-computing.

    Returns:
        str: Device identifier (max 64 chars).
    """
    explicit = (
        request.headers.get('X-Device-ID')
        or request.headers.get('X-Fingerprint')
    )
    if explicit:
        return str(explicit)[:64]

    ua = request.META.get('HTTP_USER_AGENT', '')
    ip = _get_client_ip(request)
    fingerprint = hashlib.sha256(
        f"{ua}|{ip}".encode()
    ).hexdigest()[:20]
    return f'fp:{fingerprint}'


def _get_user_context(request):
    """
    Safely extract (user_id, role) from the request.

    Returns:
        tuple[str, str]: (user_id, user_role)
    """
    try:
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return 'anonymous', 'anonymous'
        uid = str(getattr(user, 'pk', '?'))
        role = getattr(user, 'role', None) or (
            'superadmin' if getattr(user, 'is_superuser', False)
            else 'staff' if getattr(user, 'is_staff', False)
            else 'authenticated'
        )
        return uid, role
    except Exception:  # noqa: BLE001
        return 'unknown', 'unknown'


def _get_session_key(request):
    """Return the first 16 chars of the session key, or '-'."""
    try:
        key = request.session.session_key or ''
        return key[:16] if key else '-'
    except Exception:  # noqa: BLE001
        return '-'


# ================================================================
# 3. SECURITY AUDIT MIDDLEWARE
# ================================================================

class SecurityAuditMiddleware:
    """
    Production security audit log — captures every HTTP request.

    Every request through the Fashionistar API is recorded with:

    ┌─────────────────────────────────────────────────────────────┐
    │ Field           │ Source                                    │
    ├─────────────────┼───────────────────────────────────────────┤
    │ request_id      │ X-Request-ID header (middleware 1)        │
    │ device_id       │ X-Device-ID header or UA+IP fingerprint   │
    │ session         │ Django session key (first 16 chars)       │
    │ client_ip       │ X-Forwarded-For → REMOTE_ADDR             │
    │ method          │ request.method (GET/POST/PUT/DELETE…)     │
    │ path            │ request.get_full_path() (includes ?query) │
    │ status          │ HTTP response status code                 │
    │ duration_ms     │ Wall-clock time in milliseconds           │
    │ user_id         │ request.user.pk or 'anonymous'            │
    │ role            │ user.role or superadmin/staff/anonymous   │
    │ user_agent      │ HTTP_USER_AGENT header (first 300 chars)  │
    │ referrer        │ HTTP_REFERER header                       │
    └─────────────────┴───────────────────────────────────────────┘

    Log levels:
        INFO    — 2xx, 3xx (normal traffic)
        WARNING — 401, 403 (auth/permission failures)
        ERROR   — 5xx (server errors, alert-worthy)

    Uses the ``security`` logger (separate from ``application``)
    so security events can be routed to a dedicated SIEM sink
    (Datadog, Elasticsearch, Cloudwatch Security Lake) without
    mixing with normal application logs.

    Example log line (INFO)::

        SECURITY_AUDIT action=REQUEST req=abc-123
        device=fp:a1b2c3d4e5 session=abcdef123456 ip=102.89.45.1
        method=POST path=/api/v2/auth/login/ status=200
        duration_ms=42.3 user_id=FASTAR-X9K4 role=client
        ua='Mozilla/5.0...' referrer=-

    Example log line (WARNING — 403)::

        SECURITY_AUDIT action=PERMISSION_DENIED req=abc-123
        device=fp:x9y8z7 session=- ip=77.12.55.200
        method=DELETE path=/api/v2/admin/users/42/
        status=403 duration_ms=18.1 user_id=FASTAR-R2M7
        role=client ua='curl/7.88.1' referrer=-
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()

        # Resolve & store device_id early — views can read
        # request.device_id without re-computing.
        device_id = _get_device_id(request)
        request.device_id = device_id

        response = self.get_response(request)

        duration_ms = (time.monotonic() - start) * 1000
        status_code = response.status_code
        client_ip = _get_client_ip(request)
        user_id, role = _get_user_context(request)
        request_id = getattr(request, 'request_id', '-')
        session_key = _get_session_key(request)
        path = request.get_full_path()
        ua = request.META.get('HTTP_USER_AGENT', '-')[:300]
        referrer = request.META.get('HTTP_REFERER', '-')[:200]

        if status_code in (401, 403):
            action = 'PERMISSION_DENIED'
        elif status_code >= 500:
            action = 'SERVER_ERROR'
        elif status_code >= 400:
            action = 'CLIENT_ERROR'
        else:
            action = 'REQUEST'

        msg = (
            "SECURITY_AUDIT action=%s req=%s device=%s session=%s "
            "ip=%s method=%s path=%s status=%d duration_ms=%.1f "
            "user_id=%s role=%s ua=%r referrer=%s"
        ) % (
            action, request_id, device_id, session_key,
            client_ip, request.method, path, status_code,
            duration_ms, user_id, role, ua, referrer,
        )

        if status_code >= 500:
            security_logger.error(msg)
        elif status_code in (401, 403):
            security_logger.warning(msg)
        else:
            security_logger.info(msg)

        return response

