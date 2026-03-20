# apps/common/models/__init__.py
"""
Models for apps.common — enterprise infrastructure models.

Exports:
  - CloudinaryProcessedWebhook: Audit trail for webhook processing
"""

from .processed_webhook import CloudinaryProcessedWebhook

__all__ = [
    "CloudinaryProcessedWebhook",
]
