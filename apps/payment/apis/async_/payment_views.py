# apps/payment/apis/async_/payment_views.py
"""
Payment Domain — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/payments/

Architecture:
  ─ All endpoints are READ-ONLY (no payment mutations).
  ─ Payment initialization and verification live on the DRF sync surface.
  ─ Each handler delegates to selectors that traverse user.payment_intents.
  ─ Zero sync_to_async: Django 6.0 native async ORM only.

Endpoints:
  GET /api/v1/ninja/payments/dashboard/ — full payment dashboard (summary + recent)
  GET /api/v1/ninja/payments/summary/   — aggregate stats
  GET /api/v1/ninja/payments/history/   — paginated payment intent list
"""
import logging

from ninja import Router
from ninja.errors import HttpError

from apps.payment.selectors import (
    aget_payment_dashboard_for_user,
    aget_payment_summary_for_user,
    aget_recent_payment_intents_for_user,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Payment — Async Dashboard"])


def _get_auth_user(request):
    """Extract the authenticated user from the Ninja request."""
    return request.auth.user if hasattr(request.auth, "user") else request.auth


# ── Full Dashboard ─────────────────────────────────────────────────────────────


@router.get("/dashboard/")
async def get_payment_dashboard(request):
    """
    GET /api/v1/ninja/payments/dashboard/

    Full payment dashboard in 2 DB queries:
    1. Aggregate stats (total, pending, succeeded amount)
    2. 5 most recent payment intents

    Response shape:
        {
          "total_count": int,
          "pending_count": int,
          "succeeded_total": "decimal_str",
          "recent_intents": [...]
        }
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        data = await aget_payment_dashboard_for_user(user)
        return {"status": "success", "data": data}
    except Exception:
        logger.exception(
            "get_payment_dashboard: unexpected error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Payment dashboard fetch failed.")


# ── Summary ────────────────────────────────────────────────────────────────────


@router.get("/summary/")
async def get_payment_summary(request):
    """
    GET /api/v1/ninja/payments/summary/

    Aggregate payment intent stats for the authenticated user.
    Returns: total_count, pending_count, succeeded_total.
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        summary = await aget_payment_summary_for_user(user)
        return {"status": "success", "data": summary}
    except Exception:
        logger.exception(
            "get_payment_summary: unexpected error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Payment summary fetch failed.")


# ── History ────────────────────────────────────────────────────────────────────


@router.get("/history/")
async def get_payment_history(request, limit: int = 10):
    """
    GET /api/v1/ninja/payments/history/?limit=10

    Most recent N payment intents for the authenticated user.
    Returns list[dict] ordered by -created_at. Max limit: 50.
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    limit = max(1, min(limit, 50))
    try:
        rows = await aget_recent_payment_intents_for_user(user, limit=limit)
        serialized = [
            {
                **row,
                "id": str(row["id"]),
                "amount": str(row["amount"]),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ]
        return {"status": "success", "data": serialized, "count": len(serialized)}
    except Exception:
        logger.exception(
            "get_payment_history: unexpected error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Payment history fetch failed.")
