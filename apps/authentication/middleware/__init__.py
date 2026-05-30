# apps/authentication/middleware/__init__.py
"""
FASHIONISTAR — Authentication Middleware Package
===================================================

Exports IdempotencyMiddleware for secure, exactly-once POST semantics.
"""

from apps.authentication.middleware.idempotency import IdempotencyMiddleware

__all__ = ["IdempotencyMiddleware"]
#added comment