# apps/kyc/tasks.py
"""
KYC Async Background Tasks — Celery Task Definitions.

These tasks are dispatched post-commit so they never observe half-written
database rows. All tasks are idempotent and safe to retry.

Tasks:
  1. set_legal_name_from_provider_response
       Called automatically when admin approves a KYC submission.
       Extracts the vendor's full legal name from the KYC provider response
       stored in KycDocument.provider_response and saves it to
       KycSubmission.legal_name. This populates the name-matching field
       used when vendors register bank accounts for payout.

       Priority: full_name > first_name+last_name from NIN/BVN/CAC provider
       response JSON keys from Dojah, Smile Identity, and Youverify.

Celery configuration: see CELERY_TASK_ROUTES in settings for queue assignment.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction

logger = logging.getLogger("application")

# Provider response field priority list.
# Different KYC providers use different keys for the resolved full name.
# We try each in sequence and use the first non-empty match.
_NAME_FIELD_PRIORITY = [
    # Dojah NIN/BVN response fields
    "full_name",
    "FullName",
    # Smile Identity
    "Name",
    "name",
    # Youverify
    "fullName",
    # Fallback: compose from parts
    "__compose__",  # special sentinel: build from first_name + last_name
]

# Fields to compose the name from when no direct full_name key exists
_FIRST_NAME_FIELDS = ["first_name", "FirstName", "firstName", "given_name"]
_LAST_NAME_FIELDS  = ["last_name",  "LastName",  "lastName",  "surname", "family_name"]


def _extract_name_from_provider_response(provider_response: dict) -> str:
    """
    Extract the full legal name from a KYC provider response JSON blob.

    Priority: full_name > FullName > Name > name > composed first+last name.
    Returns an empty string if no name can be extracted.
    """
    if not isinstance(provider_response, dict):
        return ""

    # Check raw_response sub-key first (our canonical wrapper)
    raw = provider_response.get("raw_response", provider_response)
    if not isinstance(raw, dict):
        raw = provider_response

    for field in _NAME_FIELD_PRIORITY:
        if field == "__compose__":
            # Fallback: compose first + last name
            first = next((raw.get(f, "") for f in _FIRST_NAME_FIELDS if raw.get(f)), "")
            last  = next((raw.get(f, "") for f in _LAST_NAME_FIELDS  if raw.get(f)), "")
            if first or last:
                return f"{first} {last}".strip().upper()
        else:
            val = raw.get(field, "")
            if val and isinstance(val, str) and val.strip():
                return val.strip().upper()

    return ""


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="apps.kyc.tasks.set_legal_name_from_provider_response",
)
def set_legal_name_from_provider_response(self, submission_id: str) -> None:
    """
    Async Celery task: populate KycSubmission.legal_name from provider response.

    Triggered automatically by the post_save signal on KycSubmission when
    the status transitions to APPROVED. Admin staff do NOT need to manually
    type the legal name — the task extracts it from the provider verification
    response that was stored at document upload time.

    Args:
        submission_id: UUID string of the KycSubmission to process.

    Behaviour:
        - Skips if legal_name is already populated (idempotent).
        - Checks all KycDocument records attached to the submission.
        - Priority: NIN_CARD > BVN_SLIP > PASSPORT > DRIVERS_LICENSE > any.
        - Writes the extracted name to submission.legal_name.
        - Logs a warning if no name could be extracted (admin can fill manually).

    Retry Policy:
        - Up to 3 retries with 30-second delay.
        - Exponential backoff applied by Celery.
    """
    from apps.kyc.models import KycSubmission, KycDocument

    try:
        submission = KycSubmission.objects.select_related("user").get(pk=submission_id)
    except KycSubmission.DoesNotExist:
        logger.error(
            "set_legal_name_from_provider_response: submission %s not found", submission_id
        )
        return

    # Idempotency guard — already populated
    if submission.legal_name and submission.legal_name.strip():
        logger.info(
            "set_legal_name_from_provider_response: legal_name already set for submission=%s, skipping",
            submission_id,
        )
        return

    # Ordered priority for document type — NIN is most authoritative
    PRIORITY_TYPES = [
        "nin_card",
        "bvn_slip",
        "passport",
        "drivers_license",
        "voters_card",
        "cac_certificate",
    ]

    # Load all provider-verified documents for this submission
    documents = list(
        KycDocument.objects.filter(
            submission=submission,
            provider_verified=True,
        ).exclude(provider_response={})
    )

    if not documents:
        # Fall back to unverified documents (name may still be in response)
        documents = list(
            KycDocument.objects.filter(submission=submission)
            .exclude(provider_response={})
        )

    if not documents:
        logger.warning(
            "set_legal_name_from_provider_response: no documents with provider_response "
            "found for submission=%s — legal_name must be set manually by admin",
            submission_id,
        )
        return

    # Sort by PRIORITY_TYPES order
    def doc_priority(doc):
        try:
            return PRIORITY_TYPES.index(doc.document_type)
        except ValueError:
            return 99

    documents.sort(key=doc_priority)

    extracted_name = ""
    for doc in documents:
        extracted_name = _extract_name_from_provider_response(doc.provider_response)
        if extracted_name:
            logger.info(
                "set_legal_name_from_provider_response: extracted name '%s' from "
                "doc_type=%s for submission=%s",
                extracted_name, doc.document_type, submission_id,
            )
            break

    if not extracted_name:
        logger.warning(
            "set_legal_name_from_provider_response: could not extract legal name from "
            "any document for submission=%s — admin must fill manually",
            submission_id,
        )
        return

    with transaction.atomic():
        submission.legal_name = extracted_name
        submission.save(update_fields=["legal_name", "updated_at"])

    logger.info(
        "set_legal_name_from_provider_response: ✓ set legal_name='%s' for "
        "submission=%s (user=%s)",
        extracted_name, submission_id, submission.user_id,
    )


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="apps.kyc.tasks.sync_bank_account_kyc_match",
)
def sync_bank_account_kyc_match(self, submission_id: str) -> None:
    """
    After legal_name is populated, refresh kyc_name_matched on all the
    vendor's saved VendorBankAccount records.

    This ensures accounts added BEFORE KYC was approved get their
    kyc_name_matched flag updated retroactively.

    Args:
        submission_id: UUID string of the KycSubmission.
    """
    from apps.kyc.models import KycSubmission
    from apps.vendor.models import VendorBankAccount

    try:
        submission = KycSubmission.objects.select_related("user").get(pk=submission_id)
    except KycSubmission.DoesNotExist:
        return

    legal_name = (submission.legal_name or "").strip().lower()
    if not legal_name:
        logger.warning(
            "sync_bank_account_kyc_match: no legal_name on submission=%s, skipping",
            submission_id,
        )
        return

    try:
        vendor = submission.user.vendor_profile
    except Exception:
        return  # User is not a vendor — no accounts to update

    accounts = VendorBankAccount.objects.filter(vendor=vendor, is_deleted=False)
    updated = 0
    for account in accounts:
        account_name_lower = (account.account_name or "").strip().lower()
        matched = legal_name in account_name_lower or account_name_lower in legal_name
        if account.kyc_name_matched != matched:
            account.kyc_name_matched = matched
            account.save(update_fields=["kyc_name_matched", "updated_at"])
            updated += 1

    logger.info(
        "sync_bank_account_kyc_match: updated %d bank accounts for vendor=%s",
        updated, vendor.pk,
    )
