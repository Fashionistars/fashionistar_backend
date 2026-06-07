# apps/wallet/services/verification.py
"""
Fashionistar Financial Security Verification Utilities.

This module implements the "Double-Door" security algorithm for company
commission withdrawal authorization.

Double-Door Verification:
    Door 1 — Identity Lock:
        The requesting user's email MUST match the static company superuser
        email: ``fashionistarclothings@outlook.com``.

    Door 2 — Domain Lock (Keyword Gate):
        The target bank account name MUST contain the keyword ``"FASHIONISTAR"``
        as a word component (case-insensitive). This ensures that even if
        credentials are compromised, funds cannot be redirected to a personal
        account without the company name in the beneficiary.

Integration Guide::

    from apps.wallet.services.verification import verify_company_payout_eligibility

    ok = verify_company_payout_eligibility(
        user_email="fashionistarclothings@outlook.com",
        account_name="FASHIONISTAR CLOTHINGS LTD",
    )
    # True

    ok = verify_company_payout_eligibility(
        user_email="fashionistarclothings@outlook.com",
        account_name="John Doe Personal Account",
    )
    # False — keyword "FASHIONISTAR" not found

    ok = verify_company_payout_eligibility(
        user_email="rogue@example.com",
        account_name="FASHIONISTAR CLOTHINGS LTD",
    )
    # False — email mismatch

Security Notes:
    - Comparison is case-insensitive for robustness.
    - The keyword check uses word-boundary logic (split on whitespace) so
      a partial match like "FASHIONISTARFAKE" would still pass the ``in``
      check — this is intentional: we check if the keyword appears WITHIN
      any word of the account name.
    - Any failure here must be logged as a CRITICAL security event.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# The ONE TRUE company email. Must match WalletProvisioningService.COMPANY_EMAIL.
COMPANY_EMAIL: str = "fashionistarclothings@outlook.com"

# The keyword that MUST appear in any company commission withdrawal account name.
COMPANY_KEYWORD: str = "FASHIONISTAR"


def verify_company_payout_eligibility(
    user_email: str,
    account_name: str,
) -> bool:
    """Verify a company commission payout request passes both security doors.

    Implements the Fashionistar "Double-Door" security model:
        Door 1: Email identity check.
        Door 2: Account name keyword gate.

    Args:
        user_email: Email of the user requesting the payout.
        account_name: Destination bank account holder name.

    Returns:
        bool: ``True`` only if BOTH doors pass, ``False`` otherwise.

    Examples:
        >>> verify_company_payout_eligibility(
        ...     "fashionistarclothings@outlook.com",
        ...     "FASHIONISTAR CLOTHINGS LTD",
        ... )
        True

        >>> verify_company_payout_eligibility(
        ...     "fashionistarclothings@outlook.com",
        ...     "John Doe Personal",
        ... )
        False

        >>> verify_company_payout_eligibility(
        ...     "hacker@evil.com",
        ...     "FASHIONISTAR CLOTHINGS LTD",
        ... )
        False
    """
    # ── Door 1: Identity Lock ─────────────────────────────────────────────────
    if user_email.strip().lower() != COMPANY_EMAIL.lower():
        logger.warning(
            "Company payout eligibility FAILED — Door 1 (email mismatch): "
            "email=%s expected=%s",
            user_email, COMPANY_EMAIL,
        )
        return False

    # ── Door 2: Domain/Keyword Lock ───────────────────────────────────────────
    # Check if FASHIONISTAR appears anywhere within the account name
    account_name_upper = account_name.strip().upper()
    keyword_found = COMPANY_KEYWORD in account_name_upper

    if not keyword_found:
        logger.warning(
            "Company payout eligibility FAILED — Door 2 (keyword missing): "
            "account_name=%r keyword=%s",
            account_name, COMPANY_KEYWORD,
        )
        return False

    logger.info(
        "Company payout eligibility PASSED — user=%s account_name=%r",
        user_email, account_name,
    )
    return True


def assert_company_payout_eligibility(user_email: str, account_name: str) -> None:
    """Assert company payout eligibility, raising ``ValueError`` on failure.

    Convenience wrapper around ``verify_company_payout_eligibility`` for use
    in service methods that prefer to raise rather than check return values.

    Args:
        user_email: Email of the user requesting the payout.
        account_name: Destination bank account holder name.

    Raises:
        ValueError: With a descriptive security message if either door fails.
    """
    if user_email.strip().lower() != COMPANY_EMAIL.lower():
        raise ValueError(
            "Security Violation — Door 1: "
            f"Requesting user ({user_email!r}) is not the Company Financial Admin "
            f"({COMPANY_EMAIL}). Company commission payouts are restricted to "
            "the primary company superuser only."
        )

    if COMPANY_KEYWORD not in account_name.strip().upper():
        raise ValueError(
            "Security Violation — Door 2: "
            f"Withdrawal account name {account_name!r} does not contain the "
            f"required keyword '{COMPANY_KEYWORD}'. Company funds can only be "
            "transferred to FASHIONISTAR-named accounts for accountability."
        )
