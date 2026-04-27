# apps/notification/signals.py
"""
Notification domain signals.
Listens to cross-domain events and triggers notifications accordingly.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# NOTE: Signal-based notification dispatch is intentionally minimal here.
# Prefer the explicit service-call pattern (order_service → send_order_notification)
# over implicit signal chaining for traceability.
# Signals here are for scenarios where coupling through service is impossible.
