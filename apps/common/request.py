"""
Request helpers shared across middleware, permissions, services, and exception
handling.

These helpers intentionally stay side-effect free so they can be reused from
sync views, async-capable middleware, service layers, and error handling
without pulling in heavier request/audit modules.
"""

from __future__ import annotations


def get_client_ip(request) -> str:
    """
    Return the best-effort client IP address for a Django request.

    Preference order:
    1. Left-most ``X-Forwarded-For`` IP when the request passed through a proxy.
    2. ``REMOTE_ADDR`` from the socket connection.
    3. ``0.0.0.0`` as a stable fallback when no request context exists.
    """

    if request is None:
        return "0.0.0.0"

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR", "0.0.0.0")
