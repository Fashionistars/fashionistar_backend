# apps/common/middleware.py
"""
Production-grade Django WSGI middleware for the Fashionistar
backend.

Implements AGENT_PLAN Phase 1 Task 1.2 requirements:

    - RequestIDMiddleware: Injects a unique UUID4 per-request
      into every request and response as ``X-Request-ID``.
      Stored on ``request.request_id`` for structured logging.

    - RequestTimingMiddleware: Logs the method, path, status
      code, and wall-clock duration (ms) for every request.

Both are pure WSGI middleware — no async complexity needed
at this layer. They are compatible with Django 6.0 and work
transparently with both DRF sync views and Ninja async views.

Registration (add to ``MIDDLEWARE`` in settings.py)::

    MIDDLEWARE = [
        'apps.common.middleware.RequestIDMiddleware',
        'apps.common.middleware.RequestTimingMiddleware',
        ...
    ]

Logging::

    Structured JSON logging (via the application logger)
    is recommended. The ``request_id`` is available on
    the request object for injection into log records via
    a logging filter::

        class RequestIDFilter(logging.Filter):
            def filter(self, record):
                from threading import local
                record.request_id = getattr(
                    _thread_local, 'request_id', '-'
                )
                return True
"""

import logging
import time
import uuid

logger = logging.getLogger('application')


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


class RequestTimingMiddleware:
    """
    Log method, path, status code, and wall-clock time (ms)
    for every HTTP request.

    Output format::

        [GET] /api/v2/auth/login/ → 200 in 34.7ms [req=<uuid>]

    The ``request_id`` is included when available (set by
    ``RequestIDMiddleware`` when both are in ``MIDDLEWARE``).

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
