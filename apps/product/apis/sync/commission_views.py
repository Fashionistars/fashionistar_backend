# apps/product/apis/sync/commission_views.py
"""
DRF synchronous write views for ProductCommissionSnapshot.

RBAC:
  - Admin only: CREATE / PATCH commission snapshots.
  - Vendor: Read-only (GET delegated to Ninja async router).
  - Client: Not exposed.

Architecture:
  - All mutations wrapped in transaction.atomic().
  - Commission snapshots are append-only (new rate = new snapshot row).
  - Responses use success_response() / error_response() from apps.common.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from rest_framework import parsers, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.views import APIView

from apps.common.permissions import IsAuthenticatedAndActive
from apps.common.renderers import CustomJSONRenderer, error_response, success_response
from apps.product.models import Product, ProductCommissionSnapshot
from apps.product.selectors.product_selectors import (
    get_all_commission_snapshots,
    get_commission_snapshots_for_product,
)

logger = logging.getLogger(__name__)


class AdminCommissionSnapshotListCreateView(APIView):
    """List all commission snapshots + create new ones.

    GET  /api/v1/product/commission-snapshots/          -> admin: all snapshots
    POST /api/v1/product/commission-snapshots/          -> admin: create snapshot
    """

    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsAdminUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def get(self, request):
        """Return commission snapshot list with optional filters.

        Query params:
            product_id (str): Filter by product.
            vendor_id (str): Filter by vendor (via product).

        Args:
            request: DRF request.

        Returns:
            200 success_response with list of snapshot dicts.
        """
        product_id = request.query_params.get("product_id")
        vendor_id = request.query_params.get("vendor_id")
        qs = get_all_commission_snapshots(product_id=product_id, vendor_id=vendor_id)

        rows = []
        for s in qs:
            rows.append({
                "id": str(s.pk),
                "product_id": str(s.product_id),
                "commission_rate": str(s.commission_rate),
                "effective_from": s.effective_from.isoformat() if s.effective_from else None,
                "effective_to": s.effective_to.isoformat() if s.effective_to else None,
                "note": s.note,
                "set_by_id": str(s.set_by_id) if s.set_by_id else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            })
        return success_response(data=rows)

    def post(self, request):
        """Create a new commission snapshot for a product.

        Commission snapshots are append-only. To change a rate, create a new
        snapshot with the updated commission_rate and a new effective_from date.

        Args:
            request: DRF request with JSON body containing:
                product_id (str, required): Product UUID.
                commission_rate (str/Decimal, required): Rate as decimal (e.g. "12.50").
                effective_from (str, required): ISO 8601 datetime string.
                effective_to (str, optional): ISO 8601 end date.
                note (str, optional): Reason / notes for this rate change.

        Returns:
            201 success_response with snapshot id.
        """
        d = request.data
        product_id = d.get("product_id")
        commission_rate = d.get("commission_rate")
        effective_from = d.get("effective_from")

        if not all([product_id, commission_rate, effective_from]):
            return error_response(
                message="product_id, commission_rate, and effective_from are required.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate product exists
        try:
            product = Product.objects.get(pk=product_id, is_deleted=False)
        except Product.DoesNotExist:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)

        # Parse datetime
        try:
            eff_from = datetime.fromisoformat(str(effective_from).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return error_response(message="effective_from must be a valid ISO 8601 datetime.", status=status.HTTP_400_BAD_REQUEST)

        eff_to = None
        if d.get("effective_to"):
            try:
                eff_to = datetime.fromisoformat(str(d["effective_to"]).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return error_response(message="effective_to must be a valid ISO 8601 datetime.", status=status.HTTP_400_BAD_REQUEST)

        try:
            rate = Decimal(str(commission_rate))
        except Exception:
            return error_response(message="commission_rate must be a valid decimal.", status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                snapshot = ProductCommissionSnapshot.objects.create(
                    product=product,
                    commission_rate=rate,
                    effective_from=eff_from,
                    effective_to=eff_to,
                    note=str(d.get("note", "")),
                    set_by=request.user,
                )
            logger.info(
                "CommissionSnapshot created: id=%s product=%s rate=%s admin=%s",
                snapshot.pk, product_id, rate, request.user.pk,
            )
            return success_response(
                data={"id": str(snapshot.pk), "commission_rate": str(rate)},
                message="Commission snapshot created successfully.",
                status=status.HTTP_201_CREATED,
            )
        except Exception as exc:
            logger.error("CommissionSnapshot create failed product=%s: %s", product_id, exc)
            return error_response(message="Failed to create commission snapshot.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminCommissionSnapshotDetailView(APIView):
    """Retrieve or update a single commission snapshot.

    GET   /api/v1/product/commission-snapshots/{pk}/  -> admin only
    PATCH /api/v1/product/commission-snapshots/{pk}/  -> admin only (note / effective_to only)
    """

    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsAdminUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def _get_snapshot(self, pk):
        """Fetch snapshot by PK.

        Args:
            pk: Snapshot primary key string.

        Returns:
            ProductCommissionSnapshot or None.
        """
        try:
            return ProductCommissionSnapshot.objects.select_related("product", "set_by").get(pk=pk)
        except ProductCommissionSnapshot.DoesNotExist:
            return None

    def get(self, request, pk):
        """Return a single commission snapshot row."""
        snapshot = self._get_snapshot(pk)
        if not snapshot:
            return error_response(message="Commission snapshot not found.", status=status.HTTP_404_NOT_FOUND)
        return success_response(data={
            "id": str(snapshot.pk),
            "product_id": str(snapshot.product_id),
            "commission_rate": str(snapshot.commission_rate),
            "effective_from": snapshot.effective_from.isoformat() if snapshot.effective_from else None,
            "effective_to": snapshot.effective_to.isoformat() if snapshot.effective_to else None,
            "note": snapshot.note,
            "set_by_id": str(snapshot.set_by_id) if snapshot.set_by_id else None,
            "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        })

    def patch(self, request, pk):
        """Update mutable fields: note and effective_to only.

        Commission rate changes must create a new snapshot row (append-only policy).

        Args:
            request: DRF request with partial JSON body.
            pk: Snapshot PK string.

        Returns:
            200 success_response or error.
        """
        snapshot = self._get_snapshot(pk)
        if not snapshot:
            return error_response(message="Commission snapshot not found.", status=status.HTTP_404_NOT_FOUND)

        # Only allow note + effective_to to be mutated (rate is immutable)
        MUTABLE = {"note", "effective_to"}
        updated = []
        d = request.data

        if "note" in d:
            snapshot.note = str(d["note"])
            updated.append("note")

        if "effective_to" in d:
            if d["effective_to"] is None:
                snapshot.effective_to = None
                updated.append("effective_to")
            else:
                try:
                    snapshot.effective_to = datetime.fromisoformat(str(d["effective_to"]).replace("Z", "+00:00"))
                    updated.append("effective_to")
                except (ValueError, TypeError):
                    return error_response(message="effective_to must be a valid ISO 8601 datetime.", status=status.HTTP_400_BAD_REQUEST)

        if not updated:
            return error_response(message="No mutable fields provided. Rate changes must create a new snapshot.", status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                snapshot.save(update_fields=updated + ["updated_at"])
            logger.info("CommissionSnapshot updated: id=%s fields=%s admin=%s", pk, updated, request.user.pk)
            return success_response(message="Commission snapshot updated successfully.")
        except Exception as exc:
            logger.error("CommissionSnapshot update failed id=%s: %s", pk, exc)
            return error_response(message="Failed to update commission snapshot.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)
