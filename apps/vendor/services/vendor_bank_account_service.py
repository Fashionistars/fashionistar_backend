# apps/vendor/services/vendor_bank_account_service.py
"""
VendorBankAccountService — CRUD + Paystack integration for vendor bank accounts.

Responsibilities:
  1. resolve_account     — Proxy Paystack /bank/resolve for account name lookup.
  2. create_bank_account — Validate limit, create Paystack recipient, encrypt account
                           number, cross-check KYC name, save VendorBankAccount.
  3. list_bank_accounts  — Return vendor's active (non-deleted) bank accounts.
  4. delete_bank_account — Soft-delete locally + delete Paystack recipient.
  5. set_default_account — Toggle is_default flag (only one at a time).

Security:
  - Account number stored encrypted (Fernet, FERNET_ENCRYPTION_KEY setting).
  - account_last4 stored in plain text for UI display only.
  - paystack_recipient_code unique across all vendors (cross-vendor duplicate guard).
  - Raw account number NEVER logged or returned in API responses.

Idempotency:
  - If Paystack returns an existing recipient_code for the same account, we update
    the existing VendorBankAccount row rather than creating a duplicate.
"""
from __future__ import annotations

import logging
from typing import Any
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction

logger = logging.getLogger("application")
paystack_logger = logging.getLogger("paystack")

PAYSTACK_BASE_URL = "https://api.paystack.co"


def _paystack_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class BankAccountLimitExceeded(Exception):
    """Raised when a vendor tries to add a 6th bank account."""


class BankAccountNotFound(Exception):
    """Raised when a bank account cannot be found or doesn't belong to the vendor."""


class PaystackRecipientError(Exception):
    """Raised when Paystack rejects a recipient create/delete call."""


class DuplicateBankAccount(Exception):
    """Raised when another vendor already owns this exact bank account."""


# ─────────────────────────────────────────────────────────────────────────────
# Fernet helpers
# ─────────────────────────────────────────────────────────────────────────────

def _encrypt_account_number(account_number: str) -> bytes:
    """Encrypt account number with Fernet. Returns encrypted bytes."""
    try:
        from cryptography.fernet import Fernet
        fernet_key = settings.FERNET_ENCRYPTION_KEY.encode()
        f = Fernet(fernet_key)
        return f.encrypt(account_number.encode())
    except Exception as exc:
        logger.warning("_encrypt_account_number: encryption failed — %s", exc)
        return b""


def decrypt_account_number(encrypted: bytes) -> str:
    """Decrypt a Fernet-encrypted account number. Returns empty string on failure."""
    if not encrypted:
        return ""
    try:
        from cryptography.fernet import Fernet
        fernet_key = settings.FERNET_ENCRYPTION_KEY.encode()
        f = Fernet(fernet_key)
        return f.decrypt(bytes(encrypted)).decode()
    except Exception as exc:
        logger.error("decrypt_account_number: decryption failed — %s", exc)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# VendorBankAccountService
# ─────────────────────────────────────────────────────────────────────────────

class VendorBankAccountService:
    """
    Service layer for VendorBankAccount CRUD with Paystack integration.

    All public methods are synchronous (DRF use). Async variants can be
    added as needed for Ninja endpoints.
    """

    MAX_ACCOUNTS = 5

    # ── ① Resolve Account Name ─────────────────────────────────────────────────

    @classmethod
    def resolve_account(
        cls,
        account_number: str,
        bank_code: str,
    ) -> dict[str, str]:
        """
        Call Paystack GET /bank/resolve to get the account holder name.

        Args:
            account_number: 10-digit NUBAN.
            bank_code: Paystack bank code (e.g. '044').

        Returns:
            dict: {"account_name": str, "account_number": str}

        Raises:
            PaystackRecipientError: If Paystack rejects or returns an error.
            requests.RequestException: On network errors.
        """
        url = f"{PAYSTACK_BASE_URL}/bank/resolve"
        params = {"account_number": account_number, "bank_code": bank_code}
        paystack_logger.info("Resolving bank account: %s (%s)", account_number[-4:], bank_code)

        try:
            resp = requests.get(url, headers=_paystack_headers(), params=params, timeout=15)
            data = resp.json()
        except requests.RequestException as exc:
            raise PaystackRecipientError(
                "Network error connecting to Paystack. Check internet connection."
            ) from exc

        if not data.get("status"):
            message = data.get("message", "Could not resolve bank account.")
            paystack_logger.error("Paystack resolve failed: %s", message)
            raise PaystackRecipientError(f"Account resolution failed: {message}")

        result = data.get("data", {})
        paystack_logger.info("Account resolved: %s", result.get("account_name", ""))
        return {
            "account_name": result.get("account_name", ""),
            "account_number": result.get("account_number", account_number),
        }

    # ── ② Create Bank Account ──────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def create_bank_account(
        cls,
        user,
        *,
        account_number: str,
        bank_code: str,
        account_name: str,
        bank_name: str,
    ) -> "VendorBankAccount":  # noqa: F821
        """
        Register a new bank account for the vendor.

        Steps:
          1. Validate 5-account limit.
          2. Call Paystack POST /transferrecipient (creates or retrieves recipient_code).
          3. Guard against cross-vendor duplicate (same recipient_code owned by another vendor).
          4. Encrypt account_number via Fernet.
          5. Cross-check account_name against KYC legal_name (advisory).
          6. Save VendorBankAccount.
          7. Mark VendorSetupState.bank_details = True.

        Args:
            user: The authenticated Django user (must have role='vendor').
            account_number: 10-digit NUBAN.
            bank_code: Paystack bank code.
            account_name: Verified name from Paystack resolve.
            bank_name: Human-readable bank name.

        Returns:
            VendorBankAccount: The newly created (or updated) bank account record.

        Raises:
            BankAccountLimitExceeded: If vendor already has MAX_ACCOUNTS accounts.
            DuplicateBankAccount: If another vendor owns this account.
            PaystackRecipientError: If Paystack rejects the recipient creation.
        """
        from apps.vendor.models import VendorProfile, VendorBankAccount
        from apps.vendor.models.vendor_bank_account import BankAccountVerificationStatus

        profile = VendorProfile.objects.select_for_update().get(user=user)

        # ── ① Limit check ─────────────────────────────────────────────────────
        existing_count = VendorBankAccount.objects.filter(
            vendor=profile,
            is_deleted=False,
        ).count()
        if existing_count >= cls.MAX_ACCOUNTS:
            raise BankAccountLimitExceeded(
                f"You can save up to {cls.MAX_ACCOUNTS} bank accounts. "
                "Please delete an existing account before adding a new one."
            )

        # ── ② Paystack recipient creation ──────────────────────────────────────
        recipient_code, paystack_verified = cls._create_paystack_recipient(
            account_number=account_number,
            bank_code=bank_code,
            account_name=account_name,
        )

        # ── ③ Cross-vendor duplicate guard ─────────────────────────────────────
        duplicate = VendorBankAccount.objects.filter(
            paystack_recipient_code=recipient_code,
            is_deleted=False,
        ).exclude(vendor=profile).first()

        if duplicate:
            raise DuplicateBankAccount(
                f"This bank account (****{account_number[-4:]}) is already registered "
                "to another vendor. If you believe this is an error, contact support."
            )

        # ── ④ Idempotency: if vendor already has this recipient, update instead ──
        existing = VendorBankAccount.objects.filter(
            vendor=profile,
            paystack_recipient_code=recipient_code,
            is_deleted=False,
        ).first()

        # ── ⑤ Encrypt account number ────────────────────────────────────────────
        account_number_enc = _encrypt_account_number(account_number)
        account_last4 = account_number[-4:] if len(account_number) >= 4 else account_number

        # ── ⑥ KYC name cross-check (advisory) ─────────────────────────────────
        kyc_name_matched = cls._check_kyc_name_match(user, account_name)

        # Determine verification status
        verification_status = (
            BankAccountVerificationStatus.VERIFIED
            if paystack_verified
            else BankAccountVerificationStatus.PENDING
        )

        if existing:
            # Update in place — same account number registered again
            existing.bank_name           = bank_name
            existing.bank_code           = bank_code
            existing.account_name        = account_name
            existing.account_number_enc  = account_number_enc
            existing.account_last4       = account_last4
            existing.kyc_name_matched    = kyc_name_matched
            existing.verification_status = verification_status
            existing.save(update_fields=[
                "bank_name", "bank_code", "account_name",
                "account_number_enc", "account_last4",
                "kyc_name_matched", "verification_status", "updated_at",
            ])
            bank_account = existing
            logger.info("VendorBankAccountService: updated existing bank account for vendor=%s", profile.pk)
        else:
            # Determine is_default: first account is always default
            is_default = existing_count == 0
            bank_account = VendorBankAccount.objects.create(
                vendor=profile,
                bank_name=bank_name,
                bank_code=bank_code,
                account_name=account_name,
                account_number_enc=account_number_enc,
                account_last4=account_last4,
                paystack_recipient_code=recipient_code,
                kyc_name_matched=kyc_name_matched,
                is_default=is_default,
                verification_status=verification_status,
            )
            logger.info("VendorBankAccountService: created bank account for vendor=%s (default=%s)", profile.pk, is_default)

        # ── ⑦ Mark onboarding step ─────────────────────────────────────────────
        try:
            profile.vendor_setup_state.mark_bank_details()
        except Exception:
            pass

        return bank_account

    # ── ③ List Bank Accounts ───────────────────────────────────────────────────

    @classmethod
    def list_bank_accounts(cls, user) -> list["VendorBankAccount"]:  # noqa: F821
        """Return the vendor's active bank accounts, default first."""
        from apps.vendor.models import VendorProfile, VendorBankAccount

        profile = VendorProfile.objects.get(user=user)
        return list(
            VendorBankAccount.objects.filter(
                vendor=profile,
                is_deleted=False,
            ).order_by("-is_default", "-created_at")
        )

    # ── ④ Delete Bank Account ──────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def delete_bank_account(cls, user, account_id: str) -> None:
        """
        Soft-delete the bank account and delete the Paystack recipient.

        Args:
            user: The authenticated vendor user.
            account_id: UUID of the VendorBankAccount to delete.

        Raises:
            BankAccountNotFound: If account doesn't exist or belongs to another vendor.
            PaystackRecipientError: If Paystack deletion fails.
        """
        from apps.vendor.models import VendorProfile, VendorBankAccount

        profile = VendorProfile.objects.get(user=user)
        try:
            account = VendorBankAccount.objects.get(
                pk=account_id,
                vendor=profile,
                is_deleted=False,
            )
        except VendorBankAccount.DoesNotExist:
            raise BankAccountNotFound("Bank account not found or does not belong to your profile.")

        # Delete Paystack recipient
        if account.paystack_recipient_code:
            cls._delete_paystack_recipient(account.paystack_recipient_code)

        # If deleting the default, promote the next account
        was_default = account.is_default
        account.soft_delete()

        if was_default:
            next_account = VendorBankAccount.objects.filter(
                vendor=profile, is_deleted=False
            ).order_by("-created_at").first()
            if next_account:
                next_account.is_default = True
                next_account.save(update_fields=["is_default", "updated_at"])

        logger.info("VendorBankAccountService: deleted bank account %s for vendor=%s", account_id, profile.pk)

    # ── ⑤ Set Default Account ─────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def set_default_account(cls, user, account_id: str) -> "VendorBankAccount":  # noqa: F821
        """
        Set a bank account as the default payout destination.

        Clears is_default on all other accounts first (inside one atomic block).

        Args:
            user: The authenticated vendor user.
            account_id: UUID of the account to set as default.

        Returns:
            VendorBankAccount: The updated account.

        Raises:
            BankAccountNotFound: If account doesn't exist or belongs to another vendor.
        """
        from apps.vendor.models import VendorProfile, VendorBankAccount

        profile = VendorProfile.objects.get(user=user)

        try:
            account = VendorBankAccount.objects.select_for_update().get(
                pk=account_id,
                vendor=profile,
                is_deleted=False,
            )
        except VendorBankAccount.DoesNotExist:
            raise BankAccountNotFound("Bank account not found or does not belong to your profile.")

        # Clear all defaults for this vendor
        VendorBankAccount.objects.filter(vendor=profile, is_deleted=False).update(is_default=False)

        # Set the chosen one
        account.is_default = True
        account.save(update_fields=["is_default", "updated_at"])

        logger.info("VendorBankAccountService: set default account %s for vendor=%s", account_id, profile.pk)
        return account

    # ── Private Helpers ────────────────────────────────────────────────────────

    @classmethod
    def _create_paystack_recipient(
        cls,
        account_number: str,
        bank_code: str,
        account_name: str,
    ) -> tuple[str, bool]:
        """
        Create a Paystack Transfer Recipient.

        Returns:
            tuple: (recipient_code, was_verified_by_paystack)

        Raises:
            PaystackRecipientError: On Paystack rejection.
        """
        url = f"{PAYSTACK_BASE_URL}/transferrecipient"
        payload = {
            "type": "nuban",
            "name": account_name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "NGN",
        }
        paystack_logger.info("Creating Paystack recipient for ****%s (%s)", account_number[-4:], bank_code)

        try:
            resp = requests.post(url, headers=_paystack_headers(), json=payload, timeout=20)
            data = resp.json()
        except requests.RequestException as exc:
            raise PaystackRecipientError(
                "Network error connecting to Paystack. Check your internet connection."
            ) from exc

        if not data.get("status"):
            message = data.get("message", "Failed to create transfer recipient.")
            paystack_logger.error("Paystack recipient creation failed: %s", message)

            # Map Paystack error messages to user-friendly ones
            if "Invalid account" in message or "account number" in message.lower():
                message = "The account number is not valid for the selected bank. Please verify and try again."
            elif "bank is currently unavailable" in message.lower():
                message = "The selected bank is currently unavailable. Please try again later."
            elif "account name" in message.lower():
                message = "The account name does not match the account number. Please verify and try again."

            raise PaystackRecipientError(message)

        recipient_data = data.get("data", {})
        recipient_code = recipient_data.get("recipient_code", "")
        paystack_logger.info("Paystack recipient created: %s", recipient_code)
        return recipient_code, True

    @classmethod
    def _delete_paystack_recipient(cls, recipient_code: str) -> None:
        """Delete a Paystack Transfer Recipient. Logs errors but does NOT raise."""
        url = f"{PAYSTACK_BASE_URL}/transferrecipient/{recipient_code}"
        paystack_logger.info("Deleting Paystack recipient: %s", recipient_code)
        try:
            resp = requests.delete(url, headers=_paystack_headers(), timeout=15)
            data = resp.json()
            if data.get("status"):
                paystack_logger.info("Paystack recipient %s deleted", recipient_code)
            else:
                paystack_logger.warning(
                    "Paystack recipient deletion returned false status for %s: %s",
                    recipient_code,
                    data.get("message", ""),
                )
        except requests.RequestException as exc:
            paystack_logger.error(
                "Failed to delete Paystack recipient %s: %s — "
                "local record will still be deleted",
                recipient_code,
                exc,
            )

    @classmethod
    def _check_kyc_name_match(cls, user, account_name: str) -> bool:
        """
        Advisory KYC name check: compare account_name to KycSubmission.legal_name.

        Returns True if names match (case-insensitive, stripped).
        Returns False if no KYC legal_name is set — does NOT block the save.
        """
        try:
            submission = user.kyc_submission  # type: ignore[attr-defined]
            legal_name = (submission.legal_name or "").strip().lower()
            if not legal_name:
                return False  # No KYC name on file — advisory only
            resolved = account_name.strip().lower()
            # Simple substring check: Paystack may return "JOHN DOE ADEBAYO"
            # while KYC may have "JOHN DOE" — we consider it a match if either
            # is a substring of the other.
            return legal_name in resolved or resolved in legal_name
        except Exception:
            return False  # KYC submission doesn't exist or field missing
