# apps/wallet/services/provisioning.py
"""
WalletProvisioningService — Idempotent wallet creation for users and the
Fashionistar company account.

Architecture:
    - ``ensure_currency``     — get_or_create Currency row (idempotent).
    - ``ensure_wallet``       — get_or_create via ``user.financial_wallets``
                                reverse FK (Wave-4 canonical traversal).
    - ``ensure_company_wallet``— singleton company wallet (user=NULL per model
                                 constraint); account_name deliberately contains
                                 "FASHIONISTAR" for downstream withdrawal gates.
    - ``get_company_user``    — fetch the primary company superuser by email.
    - ``owner_type_for_user`` — resolve WalletOwnerType from UnifiedUser.role.

All methods are safe for concurrent requests — ``get_or_create`` atomicity
guarantees no duplicate wallets under race conditions.

EventBus events emitted after DB commit:
    ``wallet.created``             — first-time user wallet provision.
    ``wallet.company_provisioned`` — first-time company wallet creation.
"""
from __future__ import annotations

import logging
import secrets
from decimal import Decimal

from django.db import transaction as db_transaction

from apps.common.events import event_bus
from apps.global_platform_settings.cache import get_platform_settings
from apps.wallet.models import Currency, Wallet, WalletOwnerType

logger = logging.getLogger(__name__)

# ── Company Identity Constant ─────────────────────────────────────────────────
# This is the ONE TRUE email for the Fashionistar company superuser.
# Referenced by CompanyPayoutService and provisioning alike.
COMPANY_EMAIL: str = "fashionistarclothings@outlook.com"

# The keyword that MUST appear in a bank account name before a company
# withdrawal is allowed (case-insensitive gate — see CompanyPayoutService).
COMPANY_KEYWORD: str = "FASHIONISTAR"


class WalletProvisioningService:
    """Idempotent wallet provisioning for users and the company account.

    All methods are safe to call multiple times — they use ``get_or_create``
    patterns internally so duplicate wallets are never created, even under
    concurrent requests.
    """

    # ── Currency ───────────────────────────────────────────────────────────────

    @staticmethod
    def ensure_currency(code: str = "NGN") -> Currency:
        """Retrieve or create a Currency record for the given ISO 4217 code.

        Args:
            code: ISO 4217 currency code (e.g. ``"NGN"``, ``"USD"``).
                Case-insensitive. Defaults to ``"NGN"``.

        Returns:
            Currency: The existing or newly created Currency instance.
        """
        code_upper = code.upper()
        try:
            cfg = get_platform_settings()
            fallback_rate = cfg.ngn_usd_rate
        except Exception:
            fallback_rate = Decimal("0.00065")

        currency, _ = Currency.objects.get_or_create(
            code=code_upper,
            defaults={
                "name": "Nigerian Naira" if code_upper == "NGN" else code_upper,
                "symbol": "₦" if code_upper == "NGN" else code_upper,
                "decimal_places": 2,
                "exchange_rate_usd": (
                    fallback_rate if code_upper == "NGN" else Decimal("1.00000000")
                ),
            },
        )
        return currency

    # ── Owner-type resolution ──────────────────────────────────────────────────

    @staticmethod
    def owner_type_for_user(user) -> str:
        """Resolve the ``WalletOwnerType`` for a given ``UnifiedUser``.

        Args:
            user: A ``UnifiedUser`` instance.

        Returns:
            str: One of the ``WalletOwnerType`` constants — ``'client'``,
                ``'vendor'``, ``'admin'``, etc.
        """
        role = getattr(user, "role", WalletOwnerType.CLIENT)
        if role in {
            WalletOwnerType.VENDOR,
            WalletOwnerType.SUPPORT,
            WalletOwnerType.EDITOR,
            WalletOwnerType.MODERATOR,
            WalletOwnerType.ADMIN,
        }:
            return role
        if role and isinstance(role, str) and role.startswith("super_"):
            return WalletOwnerType.ADMIN
        return WalletOwnerType.CLIENT

    # ── User wallet ────────────────────────────────────────────────────────────

    @classmethod
    def ensure_wallet(cls, user, currency_code: str = "NGN", request=None) -> Wallet:
        """Retrieve or create the default wallet for ``user``.

        Uses the ``user.financial_wallets`` reverse FK manager so wallet
        ownership is always bound to the authenticated user's identity.

        Args:
            user: A ``UnifiedUser`` instance.
            currency_code: ISO 4217 code for the wallet currency.
                Defaults to ``"NGN"``.
            request: Optional HTTP request for audit metadata.

        Returns:
            Wallet: The existing or newly created default wallet.
        """
        currency = cls.ensure_currency(currency_code)
        owner_type = cls.owner_type_for_user(user)

        wallet, created = user.financial_wallets.get_or_create(
            owner_type=owner_type,
            currency=currency,
            is_default=True,
            defaults={
                "name": f"{owner_type.title()} Wallet",
                "account_name": str(
                    getattr(user, "email", None)
                    or getattr(user, "phone", "")
                    or user.pk
                ),
                "account_number": f"90{secrets.randbelow(10 ** 8):08d}",
            },
        )

        if created:
            _wid = str(wallet.pk)
            _uid = str(user.pk)
            _owner = owner_type

            def _on_wallet_created():
                # Compliance audit trail
                try:
                    from apps.audit_logs.services.wallet import wallet_audit
                    wallet_audit.log_wallet_created(
                        actor=user,
                        wallet_id=_wid,
                        currency=currency_code,
                        request=request,
                    )
                except Exception:
                    logger.warning(
                        "wallet_audit.log_wallet_created failed silently",
                        exc_info=True,
                    )
                # EventBus — real-time dashboard + analytics
                event_bus.emit(
                    "wallet.created",
                    wallet_id=_wid,
                    user_id=_uid,
                    currency=currency_code,
                    owner_type=_owner,
                )

            db_transaction.on_commit(_on_wallet_created)
            logger.info(
                "Wallet provisioned: user=%s owner_type=%s wallet=%s",
                user.pk, owner_type, wallet.pk,
            )

        return wallet

    # ── Company wallet ─────────────────────────────────────────────────────────

    @classmethod
    def ensure_company_wallet(cls, currency_code: str = "NGN") -> Wallet:
        """Retrieve or create the singleton Fashionistar company wallet.

        The company wallet has ``user=NULL`` per the model constraint in
        ``Wallet.clean()``; this is an intentional, documented exception to
        the FK-based ownership pattern.

        The ``account_name`` deliberately contains ``"FASHIONISTAR"`` —
        CompanyPayoutService checks this keyword as part of the double-door
        withdrawal gate.

        Args:
            currency_code: ISO 4217 code. Defaults to ``"NGN"``.

        Returns:
            Wallet: The Fashionistar company wallet instance.
        """
        currency = cls.ensure_currency(currency_code)

        wallet, created = Wallet.objects.get_or_create(
            user=None,
            owner_type=WalletOwnerType.COMPANY,
            currency=currency,
            is_default=True,
            defaults={
                "name": "Fashionistar Company Wallet",
                # FASHIONISTAR keyword required — DO NOT change without updating
                # CompanyPayoutService.verify_company_payout_eligibility()
                "account_name": "FASHIONISTAR CLOTHINGS COMPANY",
                "account_number": "FASHIONISTAR-COMPANY-001",
                "bank_name": "Fashionistar Internal",
                "provider": "internal",
            },
        )

        if created:
            logger.info(
                "Company wallet provisioned for currency=%s wallet=%s",
                currency_code, wallet.pk,
            )
            event_bus.emit_on_commit(
                "wallet.company_provisioned",
                wallet_id=str(wallet.pk),
                currency=currency_code,
            )

        return wallet

    # ── Company user lookup ────────────────────────────────────────────────────

    @classmethod
    def get_company_user(cls):
        """Fetch the primary company superuser by the static company email.

        Returns:
            UnifiedUser | None: The company superuser, or ``None`` if not
                found (e.g. before initial setup).
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            return User.objects.get(email=COMPANY_EMAIL)
        except User.DoesNotExist:
            logger.warning(
                "Company superuser not found for email=%s — run 'make su' to create it.",
                COMPANY_EMAIL,
            )
            return None
