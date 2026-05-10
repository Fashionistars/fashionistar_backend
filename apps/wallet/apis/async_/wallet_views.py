# apps/wallet/apis/async_/wallet_views.py
"""
Wallet Domain — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/wallet/

Architecture:
  ─ All endpoints are READ-ONLY (no mutations).
  ─ Mutation endpoints (PIN set/change, topup) live on the DRF sync surface.
  ─ Each handler delegates to selectors using user.financial_wallets.
  ─ Zero sync_to_async: Django 6.0 native async ORM only.

Endpoints:
  GET /api/v1/ninja/wallet/dashboard/   — full wallet snapshot + hold stats
  GET /api/v1/ninja/wallet/balance/     — lightweight balance-only read
"""
import logging

from ninja import Router
from ninja.errors import HttpError

from apps.wallet.selectors import (
    aget_wallet_balance_for_user,
    aget_wallet_dashboard_for_user,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Wallet — Async Dashboard"])


def _get_auth_user(request):
    """Extract the authenticated user from the Ninja request."""
    return request.auth.user if hasattr(request.auth, "user") else request.auth


# ── Dashboard ──────────────────────────────────────────────────────────────────


@router.get("/dashboard/")
async def get_wallet_dashboard(request):
    """
    GET /api/v1/ninja/wallet/dashboard/

    Returns full wallet snapshot: balance fields + hold aggregates.
    Delegates to Wallet.aget_full_dashboard_data() — 2 DB queries (wallet + hold agg).

    Response JSON shape:
        {
          "id": "uuid",
          "name": str,
          "balance": "decimal_str",
          "available_balance": "decimal_str",
          "pending_balance": "decimal_str",
          "escrow_balance": "decimal_str",
          "status": str,
          "has_pin": bool,
          "currency_code": str,
          "currency_symbol": str,
          "active_holds_count": int,
          "total_held_amount": "decimal_str"
        }
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        data = await aget_wallet_dashboard_for_user(user)
        return {"status": "success", "data": data}
    except Exception:
        logger.exception("get_wallet_dashboard: unexpected error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(500, "Wallet dashboard fetch failed.")


# ── Balance ────────────────────────────────────────────────────────────────────


@router.get("/balance/")
async def get_wallet_balance(request):
    """
    GET /api/v1/ninja/wallet/balance/

    Lightweight balance snapshot — single DB query.
    Returns: balance, available_balance, pending_balance, escrow_balance, status.
    """
    user = _get_auth_user(request)
    if user is None:
        raise HttpError(401, "Authentication required.")
    try:
        snapshot = await aget_wallet_balance_for_user(user)
        return {"status": "success", "data": snapshot}
    except Exception:
        logger.exception("get_wallet_balance: unexpected error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(500, "Wallet balance fetch failed.")
