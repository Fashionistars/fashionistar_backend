# apps/transactions/apis/async_/transaction_views.py
"""
Transactions Domain — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/transactions/

Architecture:
  ─ All endpoints are READ-ONLY.
  ─ Writes (create, dispute) live on the DRF sync surface.
  ─ Each handler delegates to Transaction model-level async classmethods.
  ─ Zero sync_to_async: Django 6.0 native async ORM only.

Endpoints:
  GET /api/v1/ninja/transactions/dashboard/ — full dashboard (summary + breakdown + recent)
  GET /api/v1/ninja/transactions/summary/   — inflow/outflow/net aggregate
  GET /api/v1/ninja/transactions/recent/    — most recent N transactions
"""
import logging

from ninja import Router
from ninja.errors import HttpError

from apps.transactions.models import Transaction

logger = logging.getLogger(__name__)

router = Router(tags=["Transactions — Async Dashboard"])


def _get_auth_user(request):
    """Extract the authenticated user from the Ninja request."""
    return request.auth.user if hasattr(request.auth, "user") else request.auth


# ── Full Dashboard ─────────────────────────────────────────────────────────────


@router.get("/dashboard/")
async def get_transaction_dashboard(request):
    """
    GET /api/v1/ninja/transactions/dashboard/

    Full transaction dashboard in 3 DB queries:
    1. Inflow/outflow aggregate (completed tx only)
    2. Status breakdown count map
    3. 5 most recent transactions

    Response shape:
        {
          "inflow": "decimal_str",
          "outflow": "decimal_str",
          "net": "decimal_str",
          "count": int,
          "status_breakdown": { "completed": int, "pending": int, ... },
          "recent_transactions": [...]
        }
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        data = await Transaction.aget_full_dashboard_data(user)
        return {"status": "success", "data": data}
    except Exception:
        logger.exception(
            "get_transaction_dashboard: unexpected error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Transaction dashboard fetch failed.")


# ── Summary ────────────────────────────────────────────────────────────────────


@router.get("/summary/")
async def get_transaction_summary(request):
    """
    GET /api/v1/ninja/transactions/summary/

    Single aggregate query: completed inflow, outflow, net, count.
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        summary = await Transaction.aget_user_summary(user)
        return {"status": "success", "data": summary}
    except Exception:
        logger.exception(
            "get_transaction_summary: unexpected error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Transaction summary fetch failed.")


# ── Recent List ────────────────────────────────────────────────────────────────


@router.get("/recent/")
async def get_recent_transactions(request, limit: int = 10):
    """
    GET /api/v1/ninja/transactions/recent/?limit=10

    Most recent N transactions for the authenticated user (both sent + received).
    Returns list[dict] ordered by -created_at.
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    limit = max(1, min(limit, 50))  # Guard: 1–50
    try:
        rows = await Transaction.aget_recent_for_user(user, limit=limit)
        serialized = [
            {
                **row,
                "id": str(row["id"]),
                "amount": str(row["amount"]),
                "fee_amount": str(row["fee_amount"]),
                "net_amount": str(row["net_amount"]),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ]
        return {"status": "success", "data": serialized, "count": len(serialized)}
    except Exception:
        logger.exception(
            "get_recent_transactions: unexpected error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Recent transactions fetch failed.")
