# apps/common/schema_hooks.py
"""
FASHIONISTAR — drf-spectacular Preprocessing Hook
===================================================
Used by SPECTACULAR_SETTINGS['PREPROCESSING_HOOKS'] in base.py.

This hook filters the OpenAPI endpoints list before schema generation,
preventing the legacy store/admin_backend/vendor app URL patterns from
crashing drf-spectacular with FK resolution errors.

WHY THIS IS NEEDED:
  The legacy apps (store, admin_backend, vendor, Paystack_Webhoook_Prod,
  ShopCart, createOrder, checkout, measurements, customer) contain
  unresolved ForeignKey references (e.g. admin_backend.category) that
  cause ValueError: 'Related model cannot be resolved' during schema
  generation — making Swagger/ReDoc return HTTP 500.

  By filtering to only expose /api/v1/ and /api/v2/ routes in the schema,
  we:
    1. Keep Swagger/ReDoc working for the NEW enterprise endpoints
    2. Hide legacy URL patterns that aren't fully migrated yet
    3. Prevent FK resolution errors during schema introspection

This is a standard production pattern used by DRF + drf-spectacular when
maintaining a legacy→new migration at the URL routing level.

Usage (in base.py):
    SPECTACULAR_SETTINGS = {
        'PREPROCESSING_HOOKS': [
            'apps.common.schema_hooks.filter_auth_endpoints_only',
        ],
    }
"""

import logging
from typing import Any, List

logger = logging.getLogger(__name__)


def filter_auth_endpoints_only(
    endpoints: List[Any],
    **kwargs
) -> List[Any]:
    """
    Preprocessing hook that filters the endpoint list to only include
    endpoints under /api/v1/ and /api/v2/ (new enterprise endpoints).

    Filters OUT:
      - All legacy store/vendor/customer/payment routes
      - Any URL that triggers Django FK model resolution errors

    Keeps IN:
      - /api/v1/auth/*          (sync DRF registration, login, OTP)
      - /api/v2/*               (async Ninja endpoints, future)
      - /api/schema/swagger-ui/ (Swagger UI itself)
      - /api/schema/redoc/      (ReDoc)
      - /admin/                 (Django admin)

    Args:
        endpoints: List of (path, path_regex, method, callback) tuples
                   provided by drf-spectacular.

    Returns:
        Filtered list containing only safe-to-introspect endpoints.
    """
    # Legacy prefixes that trigger FK resolution errors or schema crashes
    LEGACY_PREFIXES = (
        '/store/',
        '/vendor/',
        '/customer/',
        '/payment',
        '/Paystack',
        '/shopCart/',
        '/ShopCart/',
        '/createOrder/',
        '/checkout/',
        '/measurements/',
        '/notification/',
        '/chat/',
        '/admin-backend/',
        '/admin_backend/',
        '/Blog/',
        '/blog/',
        '/addon/',
        '/home/',
        '/Homepage/',
        '/api/products/',
        '/api/orders/',
        '/api/payments/',
        '/api/store/',
        '/api/vendor/',
    )

    filtered = []
    skipped = 0

    for endpoint in endpoints:
        # endpoint is a tuple: (path, path_regex, method, callback)
        path = endpoint[0] if isinstance(endpoint, (list, tuple)) else getattr(endpoint, 'path', '')

        # Skip legacy URL patterns that crash schema generation
        skip = any(path.startswith(prefix) for prefix in LEGACY_PREFIXES)

        if skip:
            skipped += 1
            logger.debug("Schema hook: skipping legacy endpoint %s", path)
        else:
            filtered.append(endpoint)

    logger.info(
        "Schema preprocessing: %d endpoints kept, %d legacy skipped",
        len(filtered), skipped
    )
    return filtered
