# apps/transactions/apis/__init__.py
"""
Transactions Domain — API Sub-Package.

Exports routers for registration in the central Django URL / Ninja API router.

DRF Sync Surface (``/api/v1/transactions/``):
    Full CRUD, ledger operations, dispute management.

Django-Ninja Async Surface (``/api/v1/ninja/transactions/``):
    Read-optimised transaction history and summary queries.

Architecture:
    Write operations (escrow hold, release, refund, fee deduction) are
    exclusively handled by the DRF sync layer to guarantee DB atomicity.
    Read operations (history list, summary stats) are served by the async
    Ninja layer for maximum throughput.
"""
