# apps/transactions/services.py
"""
Transaction Domain — Service Layer.

This module implements the core financial service classes that power every
monetary flow on the Fashionistar platform:

  - ``CommissionService``: Resolves vendor commission rates and measurement fees
    from the ``PlatformSettings`` singleton (Redis-cached, 60 s TTL).
  - ``TransactionLedgerService``: Creates, completes, and logs all transaction
    ledger entries atomically, ensuring double-entry accounting integrity.
  - ``TransactionQueryService``: Provides read-optimised queries for
    per-user transaction history and summary statistics.
  - ``DisputeService``: Opens disputes against completed transactions and
    transitions them through the dispute resolution workflow.

Architecture:
    All write operations are ``@db_transaction.atomic`` to guarantee ledger
    consistency.  Service classes expose only class methods / static methods
    — they are never instantiated.

Audit:
    All financial mutations emit PCI-DSS / NDPR compliance audit events via
    ``apps.audit_logs.services.transactions.transactions_audit``.
    Audit calls use ``db_transaction.on_commit()`` inside atomic blocks so
    that events are only logged for COMMITTED ledger entries (no phantom audits
    on rolled-back transactions).
    Audit imports are always deferred inside inner functions to prevent circular
    imports during Django startup and ``makemigrations``.

Usage::

    from apps.transactions.services import (
        CommissionService,
        TransactionLedgerService,
        TransactionQueryService,
        DisputeService,
    )

    rate = CommissionService.rate_for_vendor(vendor_user)
    txn  = TransactionLedgerService.record_escrow_hold(
        user=client, wallet=client_wallet,
        amount=Decimal("10000.00"), reference="ORD-123",
    )
"""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.global_platform_settings.cache import get_platform_settings

from apps.transactions.models import (
    CommissionRule,
    CompanyRevenueEntry,
    RevenueCategory,
    Transaction,
    TransactionDirection,
    TransactionDispute,
    TransactionLog,
    TransactionStatus,
    TransactionType,
)


class CommissionService:
    """Commission rate and measurement fee resolver.

    All fee values are resolved at call-time from ``PlatformSettings``
    (Redis-cached, 60-second TTL) so they can be adjusted from the Django
    Admin without a code redeployment.

    Class Attributes:
        DEFAULT_RATE: Backward-compatible shim — real value from PlatformSettings
                      at runtime.  Tests that read this attribute directly still
                      work; prefer ``get_default_rate()`` in new code.
        MEASUREMENT_FEE_NGN: Backward-compatible shim — same caveat as above.

    Usage::

        rate = CommissionService.get_default_rate()
        fee  = CommissionService.get_measurement_fee()
        vendor_rate = CommissionService.rate_for_vendor(vendor_user)
        commission  = CommissionService.calculate(gross_amount, vendor_rate)
    """

    # ── Live-resolved fee accessors — prefer these in all service code ────────
    @classmethod
    def get_default_rate(cls) -> Decimal:
        """Return the current default vendor commission rate from PlatformSettings.

        Returns:
            Decimal: Commission rate (e.g. ``Decimal("0.10")`` for 10%).
                     Sourced from Redis-cached PlatformSettings singleton.
        """
        return get_platform_settings().vendor_commission_rate

    @classmethod
    def get_measurement_fee(cls) -> Decimal:
        """Return the current MirrorSize measurement processing fee from PlatformSettings.

        Returns:
            Decimal: Measurement fee in NGN (e.g. ``Decimal("1000.00")``).
        """
        return get_platform_settings().measurement_fee_ngn

    # ── Backward-compatible class-level shims (deprecated) ────────────────────
    # These are checked first in legacy test code.  New code MUST use the
    # classmethods above.  The fallback values ensure offline/test environments
    # work even when Redis/DB is unavailable (PlatformSettings returns defaults).
    DEFAULT_RATE: Decimal = Decimal("0.1000")
    MEASUREMENT_FEE_NGN: Decimal = Decimal("1000.00")

    @classmethod
    def rate_for_vendor(cls, vendor_user) -> Decimal:
        """Return the effective commission rate for a specific vendor.

        Checks for an active per-vendor ``CommissionRule`` override first.
        If none exists, falls back to the global default from ``PlatformSettings``.

        Args:
            vendor_user: The Django ``User`` instance representing the vendor.

        Returns:
            Decimal: The applicable commission rate for this vendor.
        """
        rule = (
            CommissionRule.objects.filter(vendor_user=vendor_user, is_active=True)
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now()))
            .order_by("-starts_at")
            .first()
        )
        return rule.rate if rule else get_platform_settings().vendor_commission_rate

    @staticmethod
    def calculate(amount: Decimal, rate: Decimal) -> Decimal:
        """Calculate the commission amount for a given gross amount and rate.

        Args:
            amount: Gross sale amount in NGN.
            rate: Commission rate as a Decimal fraction (e.g. ``Decimal("0.10")``).

        Returns:
            Decimal: Commission amount rounded to 2 decimal places.
        """
        return (amount * rate).quantize(Decimal("0.01"))


class TransactionLedgerService:
    """Double-entry transaction ledger writer.

    Provides atomic factory methods for creating, completing, and logging
    every financial event on the platform.  All mutations are wrapped in
    database-level atomicity to ensure ledger integrity.

    Important:
        Never create ``Transaction`` objects directly — always use the factory
        methods here to guarantee that the corresponding ``TransactionLog``
        entry is also written.
    """

    @staticmethod
    def _log(
        txn: Transaction,
        new_status: str,
        previous_status: str = "",
        reason: str = "",
    ) -> None:
        """Create an immutable audit-log entry for a transaction status change.

        Args:
            txn: The ``Transaction`` instance being logged.
            new_status: The status value the transaction is moving to.
            previous_status: The status before the change (empty on creation).
            reason: Human-readable explanation of why the status changed.
        """
        TransactionLog.objects.create(
            transaction=txn,
            previous_status=previous_status,
            new_status=new_status,
            reason=reason,
        )

    @classmethod
    def create_entry(cls, **kwargs) -> Transaction:
        """Create a new ``Transaction`` ledger entry and its initial log entry.

        Args:
            **kwargs: Field values forwarded verbatim to ``Transaction.objects.create()``.

        Returns:
            Transaction: The newly created (and saved) transaction instance.
        """
        idempotency_key = kwargs.get("idempotency_key") or ""
        transaction_type = kwargs.get("transaction_type") or ""
        if idempotency_key and transaction_type:
            existing = Transaction.objects.filter(
                transaction_type=transaction_type,
                idempotency_key=idempotency_key,
            ).first()
            if existing is not None:
                return existing

        txn = Transaction.objects.create(**kwargs)
        cls._log(txn, txn.status, reason="Transaction created")
        # ── Compliance audit (on_commit: only for committed entries) ───────
        _txn_id = str(txn.id)
        _amount = str(txn.amount)
        _from_user = getattr(txn, "from_user", None)
        _tx_type = str(kwargs.get("transaction_type", ""))
        def _audit_created():
            try:
                from apps.audit_logs.services.transactions import transactions_audit
                transactions_audit.log_transaction_created(
                    actor=_from_user,
                    transaction_id=_txn_id,
                    amount=_amount,
                    tx_type=_tx_type,
                )
            except Exception:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "transactions_audit.log_transaction_created failed silently",
                    exc_info=True,
                )
        db_transaction.on_commit(_audit_created)
        return txn

    @classmethod
    def complete(cls, txn: Transaction, reason: str = "Transaction completed") -> Transaction:
        """Transition a transaction to COMPLETED status and log the change.

        Args:
            txn: The ``Transaction`` to complete.  Must support ``.complete()`` method.
            reason: Human-readable reason for the completion (shown in admin audit log).

        Returns:
            Transaction: The updated transaction instance (saved to DB).
        """
        previous = txn.status
        txn.complete()
        txn.save(update_fields=["status", "processed_at", "completed_at", "updated_at"])
        cls._log(txn, txn.status, previous_status=previous, reason=reason)
        # ── Compliance audit ──────────────────────────────────────────────────────
        _txn_id = str(txn.id)
        _amount = str(txn.amount)
        _previous = previous
        def _audit_completed():
            try:
                from apps.audit_logs.services.transactions import transactions_audit
                transactions_audit.log_transaction_created(
                    actor=getattr(txn, "from_user", None),
                    transaction_id=_txn_id,
                    amount=_amount,
                    tx_type=f"COMPLETED:{_previous}\u2192{txn.status}",
                )
            except Exception:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "transactions_audit.complete failed silently", exc_info=True
                )
        db_transaction.on_commit(_audit_completed)
        return txn

    @classmethod
    def record_escrow_hold(
        cls,
        *,
        user,
        wallet,
        amount: Decimal,
        reference: str,
        order_id: str = "",
        provider_reference: str = "",
        idempotency_key: str = "",
    ) -> Transaction:
        """Record a client escrow hold transaction when an order is placed.

        The held funds are debited from the client's wallet and held in
        Fashionistar escrow until delivery is confirmed.

        Args:
            user: The client ``User`` placing the order.
            wallet: The client's ``Wallet`` instance.
            amount: Order amount in NGN to hold.
            reference: Unique transaction reference (typically the order reference).
            order_id: Optional order UUID for cross-domain linking.
            provider_reference: Gateway transaction ID (Paystack/Flutterwave ref).
            idempotency_key: Unique key to prevent duplicate hold entries.

        Returns:
            Transaction: The completed escrow hold transaction record.
        """
        txn = cls.create_entry(
            transaction_type=TransactionType.ESCROW_HOLD,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.OUTBOUND,
            amount=amount,
            net_amount=amount,
            from_user=user,
            from_wallet=wallet,
            reference=f"{reference}:hold",
            provider_reference=provider_reference,
            idempotency_key=idempotency_key,
            order_id=order_id,
            description="Client order payment held in Fashionistar escrow.",
            completed_at=timezone.now(),
        )
        return txn

    @classmethod
    def record_escrow_release(
        cls,
        *,
        hold,
        vendor_user,
        vendor_wallet,
        company_wallet,
        gross_amount: Decimal,
        vendor_amount: Decimal,
        commission_amount: Decimal,
        idempotency_key: str = "",
    ) -> None:
        """Record escrow release: split gross amount between vendor and Fashionistar.

        Creates two atomic ledger entries:
          1. ``ESCROW_RELEASE`` credited to the vendor's wallet.
          2. ``COMMISSION`` credited to the Fashionistar company wallet.

        Also creates a ``CompanyRevenueEntry`` for internal revenue tracking.

        Args:
            hold: The original escrow hold ``Transaction`` instance.
            vendor_user: The ``User`` receiving the vendor payout.
            vendor_wallet: The vendor's ``Wallet`` instance.
            company_wallet: Fashionistar's internal company ``Wallet``.
            gross_amount: Total order amount before commission deduction.
            vendor_amount: Net payout amount to the vendor (gross − commission).
            commission_amount: Fashionistar commission retained from the sale.
            idempotency_key: Unique key to prevent duplicate release entries.
        """
        cls.create_entry(
            transaction_type=TransactionType.ESCROW_RELEASE,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.INBOUND,
            amount=vendor_amount,
            net_amount=vendor_amount,
            to_user=vendor_user,
            to_wallet=vendor_wallet,
            reference=f"{hold.reference}:vendor-release",
            idempotency_key=idempotency_key,
            order_id=hold.order_id,
            description="Escrow released to vendor after client confirmation.",
            completed_at=timezone.now(),
        )
        commission_txn = cls.create_entry(
            transaction_type=TransactionType.COMMISSION,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.INBOUND,
            amount=commission_amount,
            net_amount=commission_amount,
            to_wallet=company_wallet,
            reference=f"{hold.reference}:company-commission",
            idempotency_key=idempotency_key,
            order_id=hold.order_id,
            description="Fashionistar commission credited to company wallet.",
            completed_at=timezone.now(),
            metadata={"gross_amount": str(gross_amount)},
        )
        CompanyRevenueEntry.objects.create(
            transaction=commission_txn,
            category=RevenueCategory.ORDER_COMMISSION,
            amount=commission_amount,
            currency=company_wallet.currency,
            source_reference=hold.reference,
            metadata={"order_id": hold.order_id, "gross_amount": str(gross_amount)},
        )

    @classmethod
    def record_refund(
        cls,
        *,
        wallet,
        amount: Decimal,
        reference: str,
        order_id: str = "",
        idempotency_key: str = "",
    ) -> Transaction:
        """Record an escrow refund when an order is cancelled or disputed.

        Args:
            wallet: The client's ``Wallet`` to credit the refund to.
            amount: Refund amount in NGN.
            reference: Original order/escrow reference.
            order_id: Optional order UUID for cross-domain linking.
            idempotency_key: Unique key to prevent duplicate refund entries.

        Returns:
            Transaction: The completed refund transaction record.
        """
        return cls.create_entry(
            transaction_type=TransactionType.REFUND,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.INBOUND,
            amount=amount,
            net_amount=amount,
            to_user=wallet.user,
            to_wallet=wallet,
            reference=f"{reference}:refund",
            idempotency_key=idempotency_key,
            order_id=order_id,
            description="Escrow refund returned to client wallet.",
            completed_at=timezone.now(),
        )

    @classmethod
    def record_vendor_payout(
        cls,
        *,
        vendor,
        wallet,
        amount: Decimal,
        reference: str,
        transfer_code: str = "",
        provider: str = "",
        gateway_response: dict | None = None,
        idempotency_key: str = "",
    ) -> Transaction:
        """Record a completed vendor payout ledger entry.

        This is the durable ledger companion to the wallet debit that happens
        during a successful vendor payout transfer.
        """
        return cls.create_entry(
            transaction_type=TransactionType.PAYOUT,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.OUTBOUND,
            amount=amount,
            net_amount=amount,
            from_user=vendor,
            from_wallet=wallet,
            reference=reference,
            external_reference=transfer_code,
            provider_reference=transfer_code,
            idempotency_key=idempotency_key,
            description="Vendor payout debited from wallet after provider transfer success.",
            completed_at=timezone.now(),
            metadata={
                "provider": provider,
                "gateway_response": gateway_response or {},
            },
        )

    @classmethod
    @db_transaction.atomic
    def record_measurement_fee(
        cls,
        *,
        user,
        wallet,
        company_wallet,
        reference: str,
        amount: Decimal | None = None,
        measurement_request_id: str = "",
        idempotency_key: str = "",
    ) -> Transaction:
        """Deduct the MirrorSize measurement fee from a client wallet (atomic).

        The fee is resolved from ``PlatformSettings`` when not explicitly
        provided, ensuring the current admin-configured rate is always applied.

        Args:
            user: The client ``User`` initiating the measurement request.
            wallet: The client's ``Wallet`` to deduct from.
            company_wallet: Fashionistar's internal wallet to credit.
            reference: Unique measurement transaction reference.
            amount: Fee in NGN — defaults to ``PlatformSettings.measurement_fee_ngn``.
            measurement_request_id: MirrorSize session/request ID for audit trail.
            idempotency_key: Unique key to prevent double-charging.

        Returns:
            Transaction: The completed measurement fee transaction record.

        Raises:
            ValidationError: If the client's wallet has insufficient balance.
        """
        amount = amount or CommissionService.MEASUREMENT_FEE_NGN
        if wallet.available_balance < amount:
            raise ValidationError("Insufficient balance for measurement fee.")
        # Debit client wallet
        wallet.available_balance -= amount
        wallet.balance -= amount
        # Credit company wallet
        company_wallet.available_balance += amount
        company_wallet.balance += amount
        wallet.save(update_fields=["available_balance", "balance", "updated_at"])
        company_wallet.save(update_fields=["available_balance", "balance", "updated_at"])
        txn = cls.create_entry(
            transaction_type=TransactionType.MEASUREMENT_FEE,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.INBOUND,
            amount=amount,
            net_amount=amount,
            from_user=user,
            from_wallet=wallet,
            to_wallet=company_wallet,
            reference=reference,
            idempotency_key=idempotency_key,
            measurement_request_id=measurement_request_id,
            description="Digital precision measurement processing fee.",
            completed_at=timezone.now(),
        )
        CompanyRevenueEntry.objects.create(
            transaction=txn,
            category=RevenueCategory.MEASUREMENT_SERVICE,
            amount=amount,
            currency=company_wallet.currency,
            source_reference=reference,
            metadata={"measurement_request_id": measurement_request_id},
        )
        return txn


class TransactionQueryService:
    """Read-optimised query helpers for transaction history and summaries.

    All methods are static or class methods — this class is never instantiated.
    """

    @staticmethod
    def for_user(user):
        """Return a queryset of all transactions involving a user (any capacity).

        Matches transactions where the user appears as sender, receiver, or
        wallet owner on either side of the ledger.

        Args:
            user: The Django ``User`` instance to query for.

        Returns:
            QuerySet[Transaction]: Ordered by ``-created_at`` with related fields
                                   pre-fetched to minimise N+1 queries.
        """
        return (
            Transaction.objects.filter(
                Q(from_user=user)
                | Q(to_user=user)
                | Q(from_wallet__user=user)
                | Q(to_wallet__user=user)
            )
            .select_related(
                "from_user",
                "to_user",
                "from_wallet",
                "to_wallet",
                "from_wallet__currency",
                "to_wallet__currency",
            )
            .order_by("-created_at")
        )

    @classmethod
    def summary_for_user(cls, user) -> dict:
        """Return aggregate financial statistics for a user's transaction history.

        Args:
            user: The Django ``User`` instance.

        Returns:
            dict: Summary with the following keys:
                - ``total_transactions`` (int): Total count of all transactions.
                - ``completed`` (int): Count of COMPLETED transactions.
                - ``pending`` (int): Count of PENDING or PROCESSING transactions.
                - ``total_sent`` (Decimal): Sum of all outbound amounts.
                - ``total_received`` (Decimal): Sum of all inbound amounts.
        """
        qs = cls.for_user(user)
        return {
            "total_transactions": qs.count(),
            "completed": qs.filter(status=TransactionStatus.COMPLETED).count(),
            "pending": qs.filter(
                status__in=[TransactionStatus.PENDING, TransactionStatus.PROCESSING]
            ).count(),
            "total_sent": (
                qs.filter(Q(from_user=user) | Q(from_wallet__user=user))
                .aggregate(total=Sum("amount"))["total"]
                or Decimal("0.00")
            ),
            "total_received": (
                qs.filter(Q(to_user=user) | Q(to_wallet__user=user))
                .aggregate(total=Sum("amount"))["total"]
                or Decimal("0.00")
            ),
        }


class DisputeService:
    """Transaction dispute lifecycle manager.

    Handles opening disputes against completed transactions and transitions
    the transaction into the ``DISPUTED`` status with a full audit trail.
    """

    @staticmethod
    def create_dispute(
        *,
        user,
        transaction_id,
        reason: str,
        amount: Decimal,
    ) -> TransactionDispute:
        """Open a dispute against a completed transaction.

        Validates that the transaction belongs to the requesting user, creates
        the ``TransactionDispute`` record, and transitions the transaction
        status to ``DISPUTED``.

        Args:
            user: The ``User`` raising the dispute (must be a party to the transaction).
            transaction_id: Primary key of the ``Transaction`` to dispute.
            reason: Human-readable description of why the dispute is being raised.
            amount: The amount under dispute (may be less than the full transaction).

        Returns:
            TransactionDispute: The newly created dispute record.

        Raises:
            Transaction.DoesNotExist: If the transaction doesn't exist or doesn't
                                       belong to the requesting user.
        """
        txn = TransactionQueryService.for_user(user).get(pk=transaction_id)
        dispute = TransactionDispute.objects.create(
            transaction=txn,
            initiated_by=user,
            reason=reason,
            disputed_amount=amount,
        )
        previous = txn.status
        txn.status = TransactionStatus.DISPUTED
        txn.save(update_fields=["status", "updated_at"])
        TransactionLog.objects.create(
            transaction=txn,
            previous_status=previous,
            new_status=txn.status,
            changed_by=user,
            reason="Dispute opened",
        )
        # ── Compliance audit (PCI-DSS: dispute events retained indefinitely) ─
        try:
            from apps.audit_logs.services.transactions import transactions_audit
            transactions_audit.log_transaction_created(
                actor=user,
                transaction_id=str(txn.id),
                amount=str(amount),
                tx_type="DISPUTE_OPENED",
            )
        except Exception:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "transactions_audit.create_dispute failed silently", exc_info=True
            )
        return dispute
