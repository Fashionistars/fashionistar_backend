"""Wallet selectors for canonical read-only Wave 4 endpoints.

All user-owned wallet reads start from the authenticated user reverse manager
``user.financial_wallets``. API handlers import this selector module instead
of importing wallet models so read logic stays centralized and testable.
"""

from __future__ import annotations

import asyncio
from typing import Any


def get_wallet_dashboard_for_user(user) -> dict[str, Any]:
    """Return a user wallet dashboard snapshot for sync compatibility reads.

    Args:
        user: Authenticated Django user.

    Returns:
        dict[str, Any]: Balance fields plus active escrow hold statistics.
    """
    wallet_model = user.financial_wallets.model
    return {
        **wallet_model.get_balance_snapshot(user),
        **wallet_model.get_hold_stats(user),
    }


async def aget_wallet_balance_for_user(user) -> dict[str, Any]:
    """Return the lightweight async balance snapshot for a user.

    Args:
        user: Authenticated user from Ninja ``request.auth``.

    Returns:
        dict[str, Any]: Wallet balance and currency metadata.
    """
    return await user.financial_wallets.model.aget_balance_snapshot(user)


async def aget_wallet_hold_stats_for_user(user) -> dict[str, Any]:
    """Return active escrow hold statistics for a user.

    Args:
        user: Authenticated user from Ninja ``request.auth``.

    Returns:
        dict[str, Any]: Active hold count and total held amount.
    """
    return await user.financial_wallets.model.aget_hold_stats(user)


async def aget_wallet_dashboard_for_user(user) -> dict[str, Any]:
    """Return the full wallet dashboard with independent async reads.

    Args:
        user: Authenticated user from Ninja ``request.auth``.

    Returns:
        dict[str, Any]: Balance snapshot plus active hold aggregate.
    """
    # Balance and hold aggregates are independent reads, so asyncio.gather
    # reduces wall time while preserving native async ORM in both branches.
    balance, holds = await asyncio.gather(
        aget_wallet_balance_for_user(user),
        aget_wallet_hold_stats_for_user(user),
    )
    return {**balance, **holds}
