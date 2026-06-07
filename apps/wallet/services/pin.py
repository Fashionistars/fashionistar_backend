# apps/wallet/services/pin.py
"""
WalletPinService — Transaction PIN Management for Fashionistar Wallets.

Architecture:
    - PINs are bcrypt-hashed before storage via ``Wallet.set_pin()`` — the raw
      PIN is NEVER persisted or logged.
    - Failed attempts are tracked on the wallet row; the wallet is locked after
      5 consecutive failures (configurable in ``Wallet.verify_pin()``).
    - PIN changes emit ``security.pin_changed`` via the EventBus inside
      ``transaction.on_commit()`` for SIEM / real-time security monitoring.
    - All writes are wrapped in ``@db_transaction.atomic`` with
      ``SELECT FOR UPDATE`` to prevent concurrent PIN reset races.

Integration Guide:
    from apps.wallet.services.pin import WalletPinService

    # Set initial PIN after wallet provision
    WalletPinService.set_pin(user=request.user, raw_pin="1234")

    # Verify PIN before financial operations
    is_valid = WalletPinService.verify_pin(user=request.user, raw_pin="1234")

    # Change PIN (requires current PIN verification first)
    WalletPinService.change_pin(user=request.user, current_pin="1234", new_pin="5678")

EventBus Events (emitted on transaction.on_commit):
    ``security.pin_set``     — First-time PIN set.
    ``security.pin_changed`` — PIN successfully rotated.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction

from apps.common.events import event_bus
from apps.wallet.services.provisioning import WalletProvisioningService

logger = logging.getLogger(__name__)


class WalletPinService:
    """Transaction PIN management for wallets.

    PINs are bcrypt-hashed before storage — the raw PIN is NEVER persisted.
    Failed attempts are tracked; the wallet is locked after 5 consecutive
    failures (configurable in ``Wallet.verify_pin()``).
    """

    # ── Set PIN ────────────────────────────────────────────────────────────────

    @staticmethod
    @db_transaction.atomic
    def set_pin(user, raw_pin: str, request=None) -> "Wallet":  # noqa: F821
        """Set a new transaction PIN for the user's default wallet.

        Acquires a ``SELECT FOR UPDATE`` lock on the wallet row before
        hashing and saving to prevent concurrent PIN reset collisions.

        Args:
            user: A ``UnifiedUser`` instance.
            raw_pin: The plaintext 4–6 digit PIN to hash and store.
            request: Optional HTTP request for audit metadata.

        Returns:
            Wallet: The updated wallet instance.

        Raises:
            ValidationError: If ``raw_pin`` fails format validation inside
                ``Wallet.set_pin()``.
        """
        provisioned = WalletProvisioningService.ensure_wallet(user, request=request)
        wallet = user.financial_wallets.select_for_update().get(pk=provisioned.pk)
        wallet.set_pin(raw_pin)
        wallet.save(
            update_fields=[
                "pin_hash",
                "pin_set_at",
                "failed_pin_attempts",
                "pin_locked_until",
                "updated_at",
            ]
        )

        # ── Capture IDs before on_commit (avoid stale closure references) ──
        _wid = str(wallet.pk)
        _uid = str(user.pk)

        def _on_pin_set():
            # Compliance audit trail — permanent retention (CBN/GDPR)
            try:
                from apps.audit_logs.services.wallet import wallet_audit
                wallet_audit.log_wallet_pin_set(
                    actor=user,
                    wallet_id=_wid,
                    request=request,
                )
            except Exception:
                logger.warning(
                    "wallet_audit.log_wallet_pin_set failed silently",
                    exc_info=True,
                )
            # EventBus — real-time SIEM monitoring
            event_bus.emit(
                "security.pin_set",
                wallet_id=_wid,
                user_id=_uid,
            )

        db_transaction.on_commit(_on_pin_set)
        logger.info("Transaction PIN set: user=%s wallet=%s", user.pk, wallet.pk)
        return wallet

    # ── Verify PIN ─────────────────────────────────────────────────────────────

    @staticmethod
    def verify_pin(user, raw_pin: str, request=None) -> bool:
        """Verify a PIN against the stored bcrypt hash.

        Delegates to ``Wallet.verify_pin()`` which increments failed attempt
        counters and enforces lockout logic.

        Args:
            user: A ``UnifiedUser`` instance.
            raw_pin: The plaintext PIN to verify.
            request: Optional HTTP request for audit metadata.

        Returns:
            bool: ``True`` if the PIN matches and the wallet is not locked,
                ``False`` otherwise.
        """
        wallet = WalletProvisioningService.ensure_wallet(user, request=request)
        return wallet.verify_pin(raw_pin)

    # ── Change PIN ─────────────────────────────────────────────────────────────

    @staticmethod
    @db_transaction.atomic
    def change_pin(user, current_pin: str, new_pin: str, request=None) -> "Wallet":  # noqa: F821
        """Verify the current PIN then atomically replace it with a new one.

        Acquires ``SELECT FOR UPDATE`` lock. If ``current_pin`` fails
        verification the operation is aborted and the failed-attempt counter
        is incremented on the wallet.

        Args:
            user: A ``UnifiedUser`` instance.
            current_pin: The existing plaintext PIN for verification.
            new_pin: The new plaintext PIN to set.
            request: Optional HTTP request for audit metadata.

        Returns:
            Wallet: The updated wallet instance.

        Raises:
            ValidationError: If ``current_pin`` does not match the stored hash.
        """
        provisioned = WalletProvisioningService.ensure_wallet(user, request=request)
        wallet = user.financial_wallets.select_for_update().get(pk=provisioned.pk)

        if not wallet.verify_pin(current_pin):
            raise ValidationError("Current transaction PIN is invalid.")

        wallet.set_pin(new_pin)
        wallet.save(
            update_fields=[
                "pin_hash",
                "pin_set_at",
                "failed_pin_attempts",
                "pin_locked_until",
                "updated_at",
            ]
        )

        _wid = str(wallet.pk)
        _uid = str(user.pk)

        def _on_pin_changed():
            try:
                from apps.audit_logs.services.wallet import wallet_audit
                wallet_audit.log_wallet_pin_changed(
                    actor=user,
                    wallet_id=_wid,
                    request=request,
                )
            except Exception:
                logger.warning(
                    "wallet_audit.log_wallet_pin_changed failed silently",
                    exc_info=True,
                )
            event_bus.emit(
                "security.pin_changed",
                wallet_id=_wid,
                user_id=_uid,
            )

        db_transaction.on_commit(_on_pin_changed)
        logger.info("Transaction PIN changed: user=%s wallet=%s", user.pk, wallet.pk)
        return wallet
