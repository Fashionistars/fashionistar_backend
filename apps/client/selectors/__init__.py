# apps/client/selectors/__init__.py
"""
Client domain selector barrel.

Exports all sync and async read functions for the client domain.
"""

from apps.client.selectors.client_selectors import (
    # Sync
    get_client_profile_or_none,
    get_client_addresses,
    # Async
    aget_client_profile_or_none,
    aget_client_order_summary,
    aget_client_order_list,
    aget_client_wishlist,
    aget_client_measurement_summary,
    aget_client_addresses,
)

__all__ = [
    # Sync
    "get_client_profile_or_none",
    "get_client_addresses",
    # Async
    "aget_client_profile_or_none",
    "aget_client_order_summary",
    "aget_client_order_list",
    "aget_client_wishlist",
    "aget_client_measurement_summary",
    "aget_client_addresses",
]
