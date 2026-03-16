# apps/authentication/ninja_api.py
"""
Django Ninja API Instance — Async V1 Authentication.

All Ninja endpoints live under /api/v1/ninja/ to stay on uniform v1 versioning
and avoid URL collisions with DRF endpoints at /api/v1/auth/.

Guards against Django's double-import during ``auto_reload``, which
triggers ``ConfigError("Looks like you created multiple NinjaAPIs")``.
The module-level ``_api_instance`` pattern ensures only one NinjaAPI is
created per Python process.
"""

import logging
from ninja import NinjaAPI

logger = logging.getLogger('application')

# ── Singleton guard: Prevent double-registration on auto-reload ──────
_api_instance = None


def _get_api() -> NinjaAPI:
    """
    Returns the NinjaAPI singleton, creating it on first call.

    This avoids the ``ConfigError`` that Ninja raises when it detects
    multiple ``NinjaAPI`` objects with the same ``urls_namespace``.
    """
    global _api_instance
    if _api_instance is not None:
        return _api_instance

    from apps.authentication.apis.auth_views.async_views import (
        auth_router,
    )

    _api_instance = NinjaAPI(
        title="Fashionistar Auth API V1",
        version="1.0.0",
        description="Asynchronous Authentication API using Django Ninja — served at /api/v1/ninja/auth/",
        urls_namespace='authentication_v1',
    )
    _api_instance.add_router("", auth_router)
    logger.info("✅ NinjaAPI V1 initialized (namespace=authentication_v1, path=/api/v1/ninja/auth/)")
    return _api_instance


# ── Module-level export (used by urls.py) ────────────────────────────
api = _get_api()
