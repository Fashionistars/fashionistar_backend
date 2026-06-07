# apps/wallet/services/__init__.py
"""
FASHIONISTAR — Wallet Domain Services.
Unified Entry Point for Industrial Enterprise-Grade Financial Operations.

Service Architecture (Modular — one class per file):
    WalletProvisioningService — Idempotent wallet creation (user + company).
    WalletPinService          — Transaction PIN set, verify, change.
    WalletBalanceService      — Atomic credit, debit, p2p transfer.
    WalletWithdrawalService   — KYC-gated bank withdrawal requests (client/vendor).
    CompanyWithdrawalService  — Double-Door secured company commission payouts.
    EscrowService             — Order payment hold, release, refund.
    WalletService             — Legacy ledger pattern (WalletTransaction model).
    PayoutService             — Vendor payout request lifecycle management.

Import Convention::

    # Always import from this package — never from individual modules directly.
    from apps.wallet.services import (
        WalletProvisioningService,
        WalletPinService,
        WalletBalanceService,
        WalletWithdrawalService,
        CompanyWithdrawalService,
        EscrowService,
        WalletService,
        PayoutService,
    )

File Layout::

    services/
    ├── __init__.py           ← This file (unified exports)
    ├── provisioning.py       ← WalletProvisioningService
    ├── balance.py            ← WalletBalanceService
    ├── pin.py                ← WalletPinService
    ├── withdrawal.py         ← WalletWithdrawalService (client/vendor)
    ├── company_payout.py     ← CompanyWithdrawalService (company commissions)
    ├── escrow.py             ← EscrowService (order payment lifecycle)
    ├── verification.py       ← Double-Door security algorithm
    ├── wallet_service.py     ← WalletService (WalletTransaction ledger)
    ├── payout_service.py     ← PayoutService (PayoutRequest lifecycle)
    └── services_legacy.py    ← DEPRECATED shim (kept for backward compat)
"""

# ── Modular Service Imports ───────────────────────────────────────────────────

# Provisioning (user + company wallets, currency resolution)
from apps.wallet.services.provisioning import WalletProvisioningService

# Balance mutations (credit, debit, p2p transfer)
from apps.wallet.services.balance import WalletBalanceService

# PIN security management
from apps.wallet.services.pin import WalletPinService

# Client/Vendor KYC-gated bank withdrawals
from apps.wallet.services.withdrawal import WalletWithdrawalService

# Company commission payout (Double-Door secured)
from apps.wallet.services.company_payout import CompanyWithdrawalService

# Escrow hold/release/refund lifecycle
from apps.wallet.services.escrow import EscrowService

# Legacy WalletTransaction ledger model (still in use)
from apps.wallet.services.wallet_service import WalletService

# Vendor payout request lifecycle (PayoutRequest model)
from apps.wallet.services.payout_service import PayoutService

# Security verification utilities (importable directly when needed)
from apps.wallet.services.verification import (
    verify_company_payout_eligibility,
    assert_company_payout_eligibility,
)

__all__ = [
    # Primary service classes
    "WalletProvisioningService",
    "WalletBalanceService",
    "WalletPinService",
    "WalletWithdrawalService",
    "CompanyWithdrawalService",
    "EscrowService",
    "WalletService",
    "PayoutService",
    # Utility functions
    "verify_company_payout_eligibility",
    "assert_company_payout_eligibility",
]
