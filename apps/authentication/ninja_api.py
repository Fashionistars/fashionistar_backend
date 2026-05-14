# apps/authentication/ninja_api.py
"""
Django Ninja API Instance — Async V1 Authentication.

STATUS: Async views deprecated in Phase 7. Ninja API is kept as a stub
so urls.py doesn't break. It will be re-enabled when async measurement/
order endpoints are needed.

The NinjaAPI is instantiated with NO routers in this phase.
"""
import logging
from ninja import NinjaAPI

logger = logging.getLogger('application')

# ── Singleton guard ───────────────────────────────────────────────────────────
_api_instance = None


def _get_api() -> NinjaAPI:
    """Returns the NinjaAPI singleton (empty stub — no async routers registered)."""
    global _api_instance
    if _api_instance is not None:
        return _api_instance

    # Async auth_router removed (Phase 7 deprecation).
    # Re-wire async routers here when async auth endpoints are built.
    _api_instance = NinjaAPI(
        title="Fashionistar Auth API V1",
        version="1.0.0",
        description="Async auth endpoints — stub kept for urls.py mount at /api/v1/ninja/auth/.",
        urls_namespace='authentication_v1',
    )
    logger.info("✅ Auth NinjaAPI V1 stub initialized (namespace=authentication_v1, path=/api/v1/ninja/auth/)")
    return _api_instance


# ── Module-level export (used by apps/authentication/urls.py) ─────────────────
api = _get_api()
