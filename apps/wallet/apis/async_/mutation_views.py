# apps/wallet/apis/async_/mutation_views.py
"""
Wallet Domain — Django-Ninja Async Mutation Router.

Mounted at: /api/v1/ninja/wallet/

Architecture:
    This router handles HIGH-SECURITY write operations on the wallet domain.
    All read operations live in ``wallet_views.py`` (separate router).

    Endpoints in this module:
        POST /company/payout/    — Company commission withdrawal (Double-Door secured)

    Security layers:
        1. ``IsCompanyFinancialAdmin`` DRF permission class (API-level gate).
        2. ``CompanyWithdrawalService.request_company_payout()`` (service-level gate).
        3. Double-Door verification: email + account name keyword.
        4. ``SELECT FOR UPDATE`` row lock on company wallet before debit.
        5. ``transaction.on_commit()`` EventBus events (no phantom audits).

Integration:
    This router is registered in ``apps/wallet/apis/async_/__init__.py``
    as ``mutation_router`` and mounted in the main Ninja API configuration.

    Endpoint schema (PayoutRequestSchema):
        {
            "amount": "500000.00",
            "bank_code": "044",
            "account_number": "0123456789",
            "account_name": "FASHIONISTAR CLOTHINGS LTD",
            "idempotency_key": "optional-uuid-string"
        }

    Success response:
        {
            "status": "success",
            "data": {
                "transaction_id": "uuid",
                "reference": "company-payout:...",
                "status": "processing",
                "amount": "500000.00",
                "available_balance": "1250000.00"
            }
        }

    Error response:
        {
            "status": "error",
            "message": "Security Violation — Door 2: ..."
        }
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction as db_transaction
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import field_validator

logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────────────────────

router = Router(tags=["Wallet — Mutations"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class CompanyPayoutRequestSchema(Schema):
    """Input schema for company commission payout requests.

    Validation:
        - ``amount``: Must be a positive Decimal > 0.
        - ``bank_code``: 3-digit bank code string (e.g. "044" for Access Bank).
        - ``account_number``: 10-digit NUBAN account number.
        - ``account_name``: Must contain "FASHIONISTAR" — validated server-side.
        - ``idempotency_key``: Optional UUID for replay protection.
    """

    amount: Decimal
    bank_code: str
    account_number: str
    account_name: str
    idempotency_key: Optional[str] = ""

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Amount must be strictly positive."""
        if v <= Decimal("0"):
            raise ValueError("Withdrawal amount must be greater than zero.")
        return v

    @field_validator("bank_code")
    @classmethod
    def validate_bank_code(cls, v: str) -> str:
        """Bank code must be non-empty."""
        if not v.strip():
            raise ValueError("Bank code is required.")
        return v.strip()

    @field_validator("account_number")
    @classmethod
    def validate_account_number(cls, v: str) -> str:
        """Account number must be numeric and exactly 10 digits (NUBAN)."""
        stripped = v.strip()
        if not stripped.isdigit() or len(stripped) != 10:
            raise ValueError("Account number must be a 10-digit NUBAN number.")
        return stripped

    @field_validator("account_name")
    @classmethod
    def validate_account_name(cls, v: str) -> str:
        """Account name must be non-empty."""
        if not v.strip():
            raise ValueError("Account name is required.")
        return v.strip()


class CompanyPayoutResponseSchema(Schema):
    """Output schema for a successful company payout initiation."""

    transaction_id: str
    reference: str
    status: str
    amount: str
    available_balance: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/company/payout/")
async def request_company_commission_payout(
    request,
    data: CompanyPayoutRequestSchema,
):
    """
    POST /api/v1/ninja/wallet/company/payout/

    Initiate a company commission withdrawal to a designated company bank account.

    Security Doors:
        Door 1 — Identity Lock: requesting user must be ``fashionistarclothings@outlook.com``.
        Door 2 — Domain Lock: ``account_name`` must contain ``"FASHIONISTAR"``.

    Only the Primary Company Superuser can call this endpoint. All attempts
    by other users are logged as CRITICAL security events.

    Request Body:
        amount (Decimal): Commission amount to withdraw in NGN.
        bank_code (str): 3-digit bank code (e.g. "044" for Access Bank).
        account_number (str): 10-digit NUBAN destination account.
        account_name (str): Account holder name — MUST contain "FASHIONISTAR".
        idempotency_key (str, optional): UUID for replay protection.

    Returns:
        200: Payout successfully initiated (pending provider execution).
        400: Validation error or security violation.
        403: Unauthorized — user is not the company admin.
        500: Internal server error.
    """
    # ── Extract authenticated user ────────────────────────────────────────────
    user = request.auth.user if hasattr(request.auth, "user") else request.auth
    if user is None or not user.is_authenticated:
        raise HttpError(401, "Authentication required.")

    # ── API-level Identity Fast-Check ─────────────────────────────────────────
    # Full Double-Door validation is done inside CompanyWithdrawalService.
    # This fast-check avoids executing service logic for unauthorized users.
    from apps.wallet.services.provisioning import COMPANY_EMAIL
    if user.email.lower() != COMPANY_EMAIL.lower():
        logger.critical(
            "SECURITY ALERT: Unauthorized company payout attempt — "
            "user=%s email=%s ip=%s",
            getattr(user, "pk", "?"),
            user.email,
            request.META.get("REMOTE_ADDR", "unknown"),
        )
        raise HttpError(
            403,
            "Forbidden: Company commission payouts are restricted to the "
            "Primary Company Financial Administrator.",
        )

    # ── Delegate to Service Layer (atomic, Double-Door secured) ───────────────
    try:
        from apps.wallet.services.company_payout import CompanyWithdrawalService
        from django.db import connection

        # Django Ninja async context — use sync_to_async for ORM operations
        # that are not yet natively async (Django 6.0 transition period)
        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: CompanyWithdrawalService.request_company_payout(
                user=user,
                amount=data.amount,
                bank_code=data.bank_code,
                account_number=data.account_number,
                account_name=data.account_name,
                idempotency_key=data.idempotency_key or "",
                request=request,
            ),
        )

        logger.info(
            "Company payout API success: user=%s txn=%s amount=%s",
            user.email, result.get("transaction_id"), data.amount,
        )
        return {"status": "success", "data": result}

    except ValueError as exc:
        # Security violation (Double-Door failure)
        logger.critical(
            "Company payout SECURITY VIOLATION: user=%s error=%s",
            user.email, str(exc),
        )
        raise HttpError(400, str(exc))

    except Exception as exc:
        from django.core.exceptions import ValidationError
        if isinstance(exc, ValidationError):
            message = exc.message if hasattr(exc, "message") else str(exc)
            raise HttpError(400, message)
        logger.exception(
            "Company payout unexpected error: user=%s amount=%s",
            user.email, data.amount,
        )
        raise HttpError(500, "Company payout processing failed. Please try again.")
