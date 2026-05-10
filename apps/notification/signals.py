# apps/notification/signals.py
"""
Notification domain signals.
Listens to cross-domain events and triggers notifications accordingly.
"""
import logging

logger = logging.getLogger(__name__)

# NOTE: Business notification dispatch is intentionally explicit. Domain
# services publish notifications through service calls, ``transaction.on_commit``,
# and EventBus-compatible handlers rather than Django model signals.
