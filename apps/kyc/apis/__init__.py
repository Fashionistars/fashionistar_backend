# apps/kyc/apis/__init__.py
from .async_.kyc_views import router as kyc_async_router

__all__ = ["kyc_async_router"]
