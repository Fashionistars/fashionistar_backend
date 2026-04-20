# apps/authentication/middleware/__init__.py
from apps.authentication.middleware.idempotency import IdempotencyMiddleware

__all__ = ["IdempotencyMiddleware"]
