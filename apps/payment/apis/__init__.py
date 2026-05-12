# apps/payment/apis/__init__.py
from .async_.payment_views import router as payment_async_router

__all__ = ["payment_async_router"]
