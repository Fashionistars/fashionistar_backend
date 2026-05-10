"""Payment selectors for Wave 4 read-only surfaces.

The payment app keeps provider writes in synchronous services, while every
dashboard/history read travels through this module. Selectors intentionally
start from ``request.user`` reverse related managers such as
``user.payment_intents`` so callers do not import and query payment models
directly from API handlers.
"""

from __future__ import annotations

import asyncio
from typing import Any


def get_payment_intent_for_user_reference(user, reference: str):
    """Return one user-owned payment intent by provider reference.

    Traversal:
        request.user.payment_intents -> PaymentIntent

    Args:
        user: Authenticated Django user from DRF ``request.user``.
        reference: Provider/payment reference supplied by the client.

    Returns:
        PaymentIntent: The matching user-owned intent.

    Raises:
        PaymentIntent.DoesNotExist: When the reference is not owned by user.
    """
    # The reverse manager is the ownership guard. Future maintainers should
    # keep payment verification scoped from user.payment_intents so a malicious
    # user cannot probe another customer's provider reference.
    return user.payment_intents.get(reference=reference)


def get_payment_summary_for_user(user) -> dict[str, Any]:
    """Return aggregate payment stats for the authenticated user.

    Args:
        user: Authenticated Django user from DRF ``request.user``.

    Returns:
        dict[str, Any]: Counts and total succeeded amount.
    """
    return user.payment_intents.model.get_summary_for_user(user)


def get_recent_payment_intents_for_user(user, limit: int = 10) -> list[dict]:
    """Return recent payment intent rows for dashboard/history views.

    Args:
        user: Authenticated Django user from DRF ``request.user``.
        limit: Maximum number of recent records to return.

    Returns:
        list[dict]: JSON-ready intent rows ordered newest first.
    """
    return user.payment_intents.model.get_recent_for_user(user, limit=limit)


async def aget_payment_summary_for_user(user) -> dict[str, Any]:
    """Async aggregate payment stats using Django native async ORM.

    Args:
        user: Authenticated user from Ninja ``request.auth``.

    Returns:
        dict[str, Any]: Counts and total succeeded amount.
    """
    return await user.payment_intents.model.aget_summary_for_user(user)


async def aget_recent_payment_intents_for_user(user, limit: int = 10) -> list[dict]:
    """Async recent payment intent rows through ``user.payment_intents``.

    Args:
        user: Authenticated user from Ninja ``request.auth``.
        limit: Maximum number of recent records to return.

    Returns:
        list[dict]: JSON-ready intent rows ordered newest first.
    """
    return await user.payment_intents.model.aget_recent_for_user(user, limit=limit)


async def aget_payment_dashboard_for_user(user) -> dict[str, Any]:
    """Return the full payment dashboard using two independent async reads.

    Args:
        user: Authenticated user from Ninja ``request.auth``.

    Returns:
        dict[str, Any]: Summary metrics plus the five most recent intents.
    """
    # Summary and recent history do not depend on each other, so gather them
    # concurrently while each branch still uses native Django async ORM.
    summary, recent = await asyncio.gather(
        aget_payment_summary_for_user(user),
        aget_recent_payment_intents_for_user(user, limit=5),
    )
    return {
        **summary,
        "recent_intents": [
            {
                **row,
                "id": str(row["id"]),
                "amount": str(row["amount"]),
                "created_at": row["created_at"].isoformat()
                if row.get("created_at")
                else None,
            }
            for row in recent
        ],
    }
