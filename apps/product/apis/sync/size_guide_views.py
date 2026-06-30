# apps/product/apis/sync/size_guide_views.py
"""
DRF synchronous write views for ProductSizeAndMeasurementGuide.

RBAC:
  - Vendor: CREATE / PATCH / DELETE their own templates.
  - Admin:  Full CRUD over all vendors templates.
  - Client: Read-only (GET endpoints live in the Ninja async router).

Architecture:
  - Views are THIN - all business logic lives in the service layer.
  - All writes use transaction.atomic() enforced at this boundary.
  - Responses always use success_response() / error_response().
  - Permissions inherited from apps.common.permissions.
"""

from __future__ import annotations

import logging

from django.db import transaction
from rest_framework import parsers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.views import APIView

from apps.common.permissions import IsAuthenticatedAndActive, IsVendor
from apps.common.renderers import CustomJSONRenderer, error_response, success_response
from apps.product.models import ProductSizeAndMeasurementGuide
from apps.product.selectors.product_selectors import (
    get_all_size_guides,
    get_size_guide_detail,
    get_size_guides_for_vendor,
)

logger = logging.getLogger(__name__)


class VendorSizeGuideListCreateView(APIView):
    """List + Create size guides.

    GET  /api/v1/product/size-guides/   -> vendor: own list; admin: all
    POST /api/v1/product/size-guides/   -> vendor: create new template
    """

    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def get(self, request):
        """Return size guide list scoped by role.

        Args:
            request: DRF request with authenticated user.

        Returns:
            200 success_response with list of guide dicts.
        """
        is_admin = request.user.is_staff or request.user.is_superuser
        if is_admin:
            qs = get_all_size_guides()
        else:
            vendor_profile = getattr(request.user, "vendor_profile", None)
            if not vendor_profile:
                return error_response(message="Vendor profile not found.", status=status.HTTP_403_FORBIDDEN)
            qs = get_size_guides_for_vendor(vendor_profile.pk)

        rows = []
        for g in qs:
            rows.append({
                "id": str(g.pk),
                "name": g.name,
                "description": g.description,
                "size_label": g.size_label,
                "chest_cm": g.chest_cm,
                "waist_cm": g.waist_cm,
                "hip_cm": g.hip_cm,
                "length_cm": g.length_cm,
                "shoulder_cm": g.shoulder_cm,
                "sleeve_cm": g.sleeve_cm,
                "inseam_cm": g.inseam_cm,
                "foot_length_cm": g.foot_length_cm,
                "sort_order": g.sort_order,
                "is_default": g.is_default,
                "save_as_template": g.save_as_template,
            })
        return success_response(data=rows)

    def post(self, request):
        """Create a new size guide template.

        Args:
            request: DRF request with JSON body.

        Returns:
            201 success_response with created guide id.
        """
        vendor_profile = getattr(request.user, "vendor_profile", None)
        if not vendor_profile:
            return error_response(message="Vendor profile not found.", status=status.HTTP_403_FORBIDDEN)

        name = (request.data.get("name") or "").strip()
        if not name:
            return error_response(message="name is required.", status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                guide = ProductSizeAndMeasurementGuide.objects.create(
                    vendor=vendor_profile,
                    name=name,
                    description=request.data.get("description", "custom"),
                    size_label=request.data.get("size_label", "M"),
                    chest_cm=request.data.get("chest_cm", ""),
                    waist_cm=request.data.get("waist_cm", ""),
                    hip_cm=request.data.get("hip_cm", ""),
                    length_cm=request.data.get("length_cm", ""),
                    shoulder_cm=request.data.get("shoulder_cm", ""),
                    sleeve_cm=request.data.get("sleeve_cm", ""),
                    inseam_cm=request.data.get("inseam_cm", ""),
                    foot_length_cm=request.data.get("foot_length_cm", ""),
                    sort_order=int(request.data.get("sort_order", 0)),
                    is_default=bool(request.data.get("is_default", False)),
                    save_as_template=bool(request.data.get("save_as_template", True)),
                )
            logger.info("SizeGuide created: id=%s vendor=%s user=%s", guide.pk, vendor_profile.pk, request.user.pk)
            return success_response(
                data={"id": str(guide.pk), "name": guide.name},
                message="Size guide created successfully.",
                status=status.HTTP_201_CREATED,
            )
        except Exception as exc:
            logger.error("SizeGuide create failed user=%s: %s", request.user.pk, exc)
            return error_response(message="Failed to create size guide.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VendorSizeGuideDetailView(APIView):
    """Retrieve, update, or soft-delete a single size guide.

    GET    /api/v1/product/size-guides/{pk}/  -> vendor: own; admin: any
    PATCH  /api/v1/product/size-guides/{pk}/  -> vendor: own; admin: any
    DELETE /api/v1/product/size-guides/{pk}/  -> vendor: own; admin: any
    """

    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def _get_guide(self, pk, user):
        """Fetch guide with ownership enforcement.

        Args:
            pk: Guide PK string.
            user: Calling UnifiedUser.

        Returns:
            ProductSizeAndMeasurementGuide or None.
        """
        if user.is_staff or user.is_superuser:
            return get_size_guide_detail(pk)
        vp = getattr(user, "vendor_profile", None)
        if not vp:
            return None
        return get_size_guide_detail(pk, vendor_id=vp.pk)

    def get(self, request, pk):
        """Return a single size guide row."""
        guide = self._get_guide(pk, request.user)
        if not guide:
            return error_response(message="Size guide not found.", status=status.HTTP_404_NOT_FOUND)
        return success_response(data={
            "id": str(guide.pk), "name": guide.name, "description": guide.description,
            "size_label": guide.size_label, "chest_cm": guide.chest_cm, "waist_cm": guide.waist_cm,
            "hip_cm": guide.hip_cm, "length_cm": guide.length_cm, "shoulder_cm": guide.shoulder_cm,
            "sleeve_cm": guide.sleeve_cm, "inseam_cm": guide.inseam_cm,
            "foot_length_cm": guide.foot_length_cm, "sort_order": guide.sort_order,
            "is_default": guide.is_default, "save_as_template": guide.save_as_template,
        })

    def patch(self, request, pk):
        """Partially update a size guide template."""
        guide = self._get_guide(pk, request.user)
        if not guide:
            return error_response(message="Size guide not found.", status=status.HTTP_404_NOT_FOUND)

        ALLOWED = {
            "name", "description", "size_label", "chest_cm", "waist_cm",
            "hip_cm", "length_cm", "shoulder_cm", "sleeve_cm",
            "inseam_cm", "foot_length_cm", "sort_order", "is_default", "save_as_template",
        }
        updated = [f for f in ALLOWED if f in request.data]
        if not updated:
            return error_response(message="No valid fields provided.", status=status.HTTP_400_BAD_REQUEST)

        for f in updated:
            setattr(guide, f, request.data[f])

        try:
            with transaction.atomic():
                guide.save(update_fields=updated + ["updated_at"])
            logger.info("SizeGuide updated: id=%s fields=%s user=%s", pk, updated, request.user.pk)
            return success_response(message="Size guide updated successfully.")
        except Exception as exc:
            logger.error("SizeGuide update failed id=%s: %s", pk, exc)
            return error_response(message="Failed to update size guide.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Soft-delete a size guide template."""
        guide = self._get_guide(pk, request.user)
        if not guide:
            return error_response(message="Size guide not found.", status=status.HTTP_404_NOT_FOUND)
        try:
            with transaction.atomic():
                guide.delete()
            logger.info("SizeGuide deleted: id=%s user=%s", pk, request.user.pk)
            return success_response(message="Size guide deleted successfully.")
        except Exception as exc:
            logger.error("SizeGuide delete failed id=%s: %s", pk, exc)
            return error_response(message="Failed to delete size guide.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)
