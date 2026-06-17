# apps/product/services/product_draft.py
"""
Business logic for the ProductDraft domain.

Architecture — Save vs. Publish (fully decoupled):

  SAVE AS DRAFT  (publish_intent = "draft")
    Frontend calls updateDraftSession() or commitDraftSession() API.
    Backend: update_draft_session() / commit_draft_session()
    Result: payload saved in ProductDraftSession. No Product row created.

  SUBMIT FOR REVIEW  (publish_intent = "pending")
    Frontend calls createProduct() API directly
    (POST /api/v1/products/vendor/).
    Backend: VendorProductListCreateView -> create_product()
    Result: canonical Product row created. Draft is NOT involved.

Enterprise Best-Practice Compliance:
1. IDEMPOTENCY: create_draft_session deduplicates on idempotency_key.
2. ROW LOCKING: update_draft_session + commit_draft_session use
   select_for_update() to prevent concurrent save collisions.
3. HARD-DELETE: discard_draft_session permanently purges the row.
4. CIRCUIT BREAKER: all ValueError paths surface clean messages.
5. OBSERVABILITY: structured logging at every mutation point.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils.timezone import now

from apps.product.models import (
    ProductDraftStatus,
    ProductDraftSession,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@transaction.atomic
def create_draft_session(
    *,
    vendor: Any,
    draft_key: Any = None,
    idempotency_key: Any = None,
    payload: dict,
    current_step: int = 1,
) -> ProductDraftSession:
    """
    Get-or-create a product draft session for the vendor.

    Resolution priority:
      1. idempotency_key fast-path (prevents duplicates on network retry).
      2. draft_key-based get_or_create.
      3. Auto-generate a new UUID draft_key if neither is provided.

    In all "found" cases the mutable fields (payload, current_step, status,
    last_synced_at) are refreshed so the caller always receives a current
    ACTIVE session.
    """
    import uuid

    timestamp = now()

    # 1. Idempotency key fast-path
    if idempotency_key:
        try:
            existing = ProductDraftSession.objects.get(
                vendor=vendor,
                idempotency_key=idempotency_key,
            )
            # Refresh mutable state so the returned object is always current.
            existing.payload = payload
            existing.current_step = current_step
            existing.status = ProductDraftStatus.ACTIVE
            existing.last_synced_at = timestamp
            existing.save(
                update_fields=[
                    "payload",
                    "current_step",
                    "status",
                    "last_synced_at",
                    "updated_at",
                ]
            )
            return existing
        except ProductDraftSession.DoesNotExist:
            pass

    # 2. draft_key-based get_or_create
    if not draft_key:
        draft_key = uuid.uuid4()
    else:
        # Guard: if a *different vendor* already owns this draft_key, reject early.
        # We must do this before get_or_create to produce a clean ValueError
        # (rather than a DB-level IntegrityError from the unique constraint).
        try:
            existing_owner = ProductDraftSession.objects.get(draft_key=draft_key)
            vendor_pk = vendor.pk if hasattr(vendor, "pk") else vendor
            if existing_owner.vendor_id != vendor_pk:
                raise ValueError(
                    "Draft session key already exists for another vendor."
                )
        except ProductDraftSession.DoesNotExist:
            pass  # No prior owner — safe to create

    draft, created = ProductDraftSession.objects.get_or_create(
        draft_key=draft_key,
        vendor=vendor,
        defaults={
            "idempotency_key": idempotency_key,
            "payload": payload,
            "current_step": current_step,
            "status": ProductDraftStatus.ACTIVE,
            "last_synced_at": timestamp,
        },
    )

    if not created:
        # Session already exists for this vendor+key — refresh mutable state.
        draft.payload = payload
        draft.current_step = current_step
        draft.status = ProductDraftStatus.ACTIVE
        if idempotency_key:
            draft.idempotency_key = idempotency_key
        draft.last_synced_at = timestamp
        draft.save(
            update_fields=[
                "payload",
                "current_step",
                "status",
                "idempotency_key",
                "last_synced_at",
                "updated_at",
            ]
        )

    logger.info(
        "create_draft_session: draft_key=%s | created=%s | vendor=%s",
        draft.draft_key,
        created,
        vendor,
    )
    return draft


# ---------------------------------------------------------------------------
# UPDATE  (called by PATCH /vendor/drafts/<key>/ on every step navigation)
# ---------------------------------------------------------------------------

@transaction.atomic
def update_draft_session(
    *,
    draft_session: ProductDraftSession,
    payload: dict,
    current_step: int | None = None,
    idempotency_key: Any = None,
) -> ProductDraftSession:
    """
    Update a draft session's payload and step counter.

    Called by:
      - Auto-save debounce on every step navigation.
      - Manual Save click in the wizard stepper.

    Uses select_for_update() row lock to prevent concurrent write collisions.
    Does NOT create any Product row. Draft remains ACTIVE.
    """
    draft = ProductDraftSession.objects.select_for_update().get(pk=draft_session.pk)

    if draft.status != ProductDraftStatus.ACTIVE:
        raise ValueError(
            f"Cannot update draft '{draft.draft_key}' — "
            f"status is '{draft.status}', expected 'active'."
        )

    draft.payload = payload
    if current_step is not None:
        draft.current_step = current_step
    if idempotency_key:
        draft.idempotency_key = idempotency_key
    draft.last_synced_at = now()
    draft.save()

    logger.info(
        "update_draft_session: draft_key=%s | step=%s | payload_keys=%s",
        draft.draft_key,
        draft.current_step,
        list((payload or {}).keys()),
    )
    return draft


# ---------------------------------------------------------------------------
# COMMIT  (SAVE AS DRAFT path — called by POST /vendor/drafts/<key>/commit/)
# ---------------------------------------------------------------------------

@transaction.atomic
def commit_draft_session(
    *,
    draft_session: ProductDraftSession,
    request: Any = None,
) -> ProductDraftSession:
    """
    Persist the draft session payload (SAVE AS DRAFT — no product creation).

    CRITICAL ARCHITECTURE NOTE
    --------------------------
    This function deliberately does NOT create a Product row.

    Product creation is handled exclusively by create_product() which is
    called from VendorProductListCreateView (POST /api/v1/products/vendor/).

    This separation eliminates the 400 ValidationError that previously
    occurred when this function ran ProductWriteFullSerializer on an
    INCOMPLETE wizard payload (e.g., when a vendor saves mid-way through
    the 5-step form without all required publish fields present).

    What this function does:
      - Acquires a select_for_update() row lock.
      - Validates the session is still ACTIVE.
      - Refreshes last_synced_at.
      - Keeps status = ACTIVE (draft persists for future resumption).
      - Returns the updated draft session (NOT a Product).

    What happens on Submit for Review:
      The frontend detects publish_intent === "pending" and calls
      createProduct() directly. The draft is discarded client-side
      via clearDraft() after successful product creation.
    """
    
    # Apply row-level lock
    draft = ProductDraftSession.objects.select_for_update().get(pk=draft_session.pk)

    if draft.status != ProductDraftStatus.ACTIVE:
        raise ValueError(
            f"Cannot save draft '{draft.draft_key}' — "
            f"status is '{draft.status}', expected 'active'."
        )

    draft.last_synced_at = now()
    draft.save(update_fields=["last_synced_at", "updated_at"])

    logger.info(
        "commit_draft_session(save-only): draft_key=%s | step=%s | payload_keys=%s",
        draft.draft_key,
        draft.current_step,
        list((draft.payload or {}).keys()),
    )
    return draft


# ---------------------------------------------------------------------------
# DISCARD
# ---------------------------------------------------------------------------

@transaction.atomic
def discard_draft_session(*, draft_session: ProductDraftSession) -> None:
    """
    Hard-delete a draft session (permanently remove from DB).

    ProductDraftSession has no soft-delete column, so the row is
    immediately purged. Called when a vendor explicitly discards a
    draft or the frontend clears one after successful product creation.
    """
    draft = ProductDraftSession.objects.select_for_update().get(pk=draft_session.pk)
    logger.info(
        "discard_draft_session: hard-deleting draft_key=%s | vendor=%s",
        draft.draft_key,
        draft.vendor_id,
    )
    draft.delete()
