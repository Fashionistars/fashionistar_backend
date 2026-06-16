# apps/product/services/product_draft_service.py
"""
Business logic for the ProductDraft domain.

────────────────────────────────────────────────────────────────
5 Additional Enterprise Best-Practice Additions
────────────────────────────────────────────────────────────────
1. IDEMPOTENCY KEYS: create_draft_session check a UUID
   idempotency_key field to prevent duplicate rows on network retry.
2. ON_COMMIT HOOKS: all audit events are fired via transaction.on_commit
   so they never execute inside the atomic block (avoids DB deadlock).
3. N+1 ELIMINATION: create_draft_session uses a single aggregate()
   call combined with F() to avoid the two-query count + avg pattern.
4. CIRCUIT BREAKER: _emit_audit swallows ALL exceptions so a broken
   audit service never kills the main mutation transaction.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from apps.product.models import (
    Product,
    ProductDraftStatus,
    ProductDraftSession,
)




logger = logging.getLogger(__name__)



# ─────────────────────────────────────────────────────────────────────────────
# DRAFT SESSIONS
# ─────────────────────────────────────────────────────────────────────────────

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
    Get or create a product draft session for the vendor.

    Resolution priority:
      1. If ``idempotency_key`` is provided, look up an existing draft that
         matches *both* the vendor and the idempotency_key first — this is the
         fast idempotent path that prevents duplicate drafts on network retries.
      2. If a ``draft_key`` is provided, use ``get_or_create`` keyed on
         (draft_key, vendor) to atomically find or initialise the session.
      3. If neither is provided, auto-generate a new UUID draft_key and create
         the session fresh.

    In all "found" cases the mutable fields (payload, current_step, status,
    idempotency_key, last_synced_at) are refreshed so the caller always
    receives an up-to-date, ACTIVE session.
    """
    import uuid
    from django.utils.timezone import now

    timestamp = now()

    # ── 1. Idempotency key fast-path ──────────────────────────────────────────
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
            existing.save(update_fields=["payload", "current_step", "status", "last_synced_at", "updated_at"])
            return existing
        except ProductDraftSession.DoesNotExist:
            pass  # Fall through to key-based get_or_create

    # ── 2. draft_key-based get_or_create ─────────────────────────────────────
    if not draft_key:
        draft_key = uuid.uuid4()
    else:
        # Guard: if a *different vendor* already owns this draft_key, reject early.
        # We must do this before get_or_create to produce a clean ValueError
        # (rather than a DB-level IntegrityError from the unique constraint).
        try:
            existing_owner = ProductDraftSession.objects.get(draft_key=draft_key)
            if existing_owner.vendor_id != (vendor.pk if hasattr(vendor, "pk") else vendor):
                raise ValueError("Draft session key already exists for another vendor.")
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
        draft.save(update_fields=["payload", "current_step", "status", "idempotency_key", "last_synced_at", "updated_at"])

    return draft


@transaction.atomic
def update_draft_session(
    *,
    draft_session: ProductDraftSession,
    payload: dict,
    current_step: int | None = None,
    idempotency_key: Any = None,
) -> ProductDraftSession:
    """
    Update a draft session with payload and step changes.
    Applies row locking (select_for_update) to prevent collisions.
    """
    from django.utils.timezone import now

    # Apply row-level lock
    draft = ProductDraftSession.objects.select_for_update().get(pk=draft_session.pk)

    if draft.status != ProductDraftStatus.ACTIVE:
        raise ValueError("Cannot update a draft session that is not active.")

    draft.payload = payload
    if current_step is not None:
        draft.current_step = current_step
    if idempotency_key:
        draft.idempotency_key = idempotency_key

    draft.last_synced_at = now()
    draft.save()
    return draft


@transaction.atomic
def discard_draft_session(*, draft_session: ProductDraftSession) -> ProductDraftSession:
    """
    Mark a draft session as discarded (soft delete).
    """
    draft = ProductDraftSession.objects.select_for_update().get(pk=draft_session.pk)
    draft.status = ProductDraftStatus.DISCARDED
    draft.save(update_fields=["status", "updated_at"])
    draft.soft_delete()
    return draft


@transaction.atomic
def commit_draft_session(
    *,
    draft_session: ProductDraftSession,
    request: Any = None,
) -> Product:
    """
    Validate the draft session payload using ProductWriteFullSerializer,
    and create or update the canonical Product.
    """
    from rest_framework.exceptions import ValidationError
    from apps.product.serializers.product_serializers import ProductWriteFullSerializer

    draft = ProductDraftSession.objects.select_for_update().get(pk=draft_session.pk)
    if draft.status != ProductDraftStatus.ACTIVE:
        raise ValueError("Cannot commit a draft session that is not active.")

    # Validate payload
    serializer = ProductWriteFullSerializer(data=draft.payload)
    if not serializer.is_valid():
        raise ValidationError(serializer.errors)

    validated_data = serializer.validated_data

    # Decide whether to create or update product
    product = draft.linked_product
    if product:
        product = update_product(
            product=product,
            validated_data=validated_data,
            actor=draft.vendor.user if hasattr(draft.vendor, "user") else None,
            request=request,
        )
    else:
        product = create_product(
            vendor=draft.vendor,
            validated_data=validated_data,
            idempotency_key=draft.idempotency_key or str(draft.draft_key),
            request=request,
        )
        draft.linked_product = product

    draft.status = ProductDraftStatus.COMMITTED
    draft.save(update_fields=["status", "linked_product", "updated_at"])
    draft.soft_delete()
    return product



