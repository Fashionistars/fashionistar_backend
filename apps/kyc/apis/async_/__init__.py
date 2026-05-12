# apps/kyc/apis/async_/__init__.py
"""
KYC Domain — Django-Ninja Async API Sub-Package.

Exports the async router for registration in the central Ninja API router.

Mounted at: /api/v1/ninja/kyc/

Endpoints:
    GET /status/    — KYC verification status summary (2 DB queries).
    GET /documents/ — Full submission + all uploaded document records.

Note:
    All mutation endpoints (BVN submit, NIN submit, document upload) live on
    the DRF sync surface at ``/api/v1/kyc/``.  This async namespace is
    READ-ONLY by design to enforce the Fashionistar write-sync / read-async
    architectural boundary.
"""

from apps.kyc.apis.async_.kyc_views import router as kyc_async_router

__all__ = ["kyc_async_router"]
