# apps/product/apis/sync/shipping_views.py
"""
DRF synchronous write views for ProductShippingProfile.

RBAC:
  - Vendor: CREATE / PATCH their own shipping profiles.
  - Admin:  Full CRUD over all vendors shipping profiles.
  - Client: Read-only (delivered from product detail via Ninja async router).

Architecture:
  - All mutations wrapped in transaction.atomic().
  - Responses use success_response() / error_response() from apps.common.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from rest_framework import parsers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.views import APIView

from apps.common.permissions import IsAuthenticatedAndActive, IsVendor
from apps.common.renderers import CustomJSONRenderer, error_response, success_response
from apps.product.models import ProductShippingProfile
from apps.product.selectors.product_selectors import (
    get_all_shipping_profiles,
    get_shipping_profile_detail,
    get_shipping_profiles_for_vendor,
)

logger = logging.getLogger(__name__)


class VendorShippingProfileListCreateView(APIView):
    """List + Create shipping profiles.

    GET  /api/v1/product/shipping-profiles/   -> vendor: own; admin: all
    POST /api/v1/product/shipping-profiles/   -> vendor: create new profile
    """

    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def get(self, request):
        """Return shipping profile list scoped by caller role.

        Args:
            request: DRF request.

        Returns:
            200 success_response with list of profile dicts.
        """
        is_admin = request.user.is_staff or request.user.is_superuser
        if is_admin:
            qs = get_all_shipping_profiles()
        else:
            vp = getattr(request.user, "vendor_profile", None)
            if not vp:
                return error_response(message="Vendor profile not found.", status=status.HTTP_403_FORBIDDEN)
            qs = get_shipping_profiles_for_vendor(vp.pk)

        rows = []
        for p in qs:
            rows.append({
                "id": str(p.pk),
                "vendor_id": str(p.vendor_id) if p.vendor_id else None,
                "weight_kg": str(p.weight_kg),
                "length_cm": str(p.length_cm),
                "width_cm": str(p.width_cm),
                "height_cm": str(p.height_cm),
                "is_fragile": p.is_fragile,
                "requires_signature": p.requires_signature,
                "free_shipping_threshold": str(p.free_shipping_threshold) if p.free_shipping_threshold else None,
                "processing_days": p.processing_days,
            })
        return success_response(data=rows)

    def post(self, request):
        """Create a new shipping profile for the calling vendor.

        Args:
            request: DRF request with JSON body.

        Returns:
            201 success_response with created profile id.
        """
        vp = getattr(request.user, "vendor_profile", None)
        if not vp:
            return error_response(message="Vendor profile not found.", status=status.HTTP_403_FORBIDDEN)

        d = request.data
        try:
            with transaction.atomic():
                profile = ProductShippingProfile.objects.create(
                    vendor=vp,
                    weight_kg=Decimal(str(d.get("weight_kg", "0.000"))),
                    length_cm=Decimal(str(d.get("length_cm", "0.0"))),
                    width_cm=Decimal(str(d.get("width_cm", "0.0"))),
                    height_cm=Decimal(str(d.get("height_cm", "0.0"))),
                    is_fragile=bool(d.get("is_fragile", False)),
                    requires_signature=bool(d.get("requires_signature", False)),
                    restricted_countries=d.get("restricted_countries", []),
                    free_shipping_threshold=(
                        Decimal(str(d["free_shipping_threshold"]))
                        if d.get("free_shipping_threshold") else None
                    ),
                    processing_days=int(d.get("processing_days", 1)),
                )
            logger.info("ShippingProfile created: id=%s vendor=%s user=%s", profile.pk, vp.pk, request.user.pk)
            return success_response(
                data={"id": str(profile.pk)},
                message="Shipping profile created successfully.",
                status=status.HTTP_201_CREATED,
            )
        except Exception as exc:
            logger.error("ShippingProfile create failed user=%s: %s", request.user.pk, exc)
            return error_response(message="Failed to create shipping profile.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VendorShippingProfileDetailView(APIView):
    """Retrieve or update a single shipping profile.

    GET   /api/v1/product/shipping-profiles/{pk}/  -> vendor: own; admin: any
    PATCH /api/v1/product/shipping-profiles/{pk}/  -> vendor: own; admin: any
    """

    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def _get_profile(self, pk, user):
        """Fetch profile with ownership enforcement.

        Args:
            pk: Profile PK.
            user: Calling UnifiedUser.

        Returns:
            ProductShippingProfile or None.
        """
        if user.is_staff or user.is_superuser:
            return get_shipping_profile_detail(pk)
        vp = getattr(user, "vendor_profile", None)
        if not vp:
            return None
        return get_shipping_profile_detail(pk, vendor_id=vp.pk)

    def get(self, request, pk):
        """Return a single shipping profile."""
        profile = self._get_profile(pk, request.user)
        if not profile:
            return error_response(message="Shipping profile not found.", status=status.HTTP_404_NOT_FOUND)
        return success_response(data={
            "id": str(profile.pk), "weight_kg": str(profile.weight_kg),
            "length_cm": str(profile.length_cm), "width_cm": str(profile.width_cm),
            "height_cm": str(profile.height_cm), "is_fragile": profile.is_fragile,
            "requires_signature": profile.requires_signature,
            "restricted_countries": profile.restricted_countries,
            "free_shipping_threshold": str(profile.free_shipping_threshold) if profile.free_shipping_threshold else None,
            "processing_days": profile.processing_days,
        })

    def patch(self, request, pk):
        """Partially update a shipping profile."""
        profile = self._get_profile(pk, request.user)
        if not profile:
            return error_response(message="Shipping profile not found.", status=status.HTTP_404_NOT_FOUND)

        ALLOWED = {
            "weight_kg", "length_cm", "width_cm", "height_cm",
            "is_fragile", "requires_signature", "restricted_countries",
            "free_shipping_threshold", "processing_days",
        }
        DECIMAL_FIELDS = {"weight_kg", "length_cm", "width_cm", "height_cm", "free_shipping_threshold"}

        updated = []
        for f in ALLOWED:
            if f in request.data:
                val = request.data[f]
                if f in DECIMAL_FIELDS and val is not None:
                    val = Decimal(str(val))
                setattr(profile, f, val)
                updated.append(f)

        if not updated:
            return error_response(message="No valid fields provided.", status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                profile.save(update_fields=updated + ["updated_at"])
            logger.info("ShippingProfile updated: id=%s fields=%s user=%s", pk, updated, request.user.pk)
            return success_response(message="Shipping profile updated successfully.")
        except Exception as exc:
            logger.error("ShippingProfile update failed id=%s: %s", pk, exc)
            return error_response(message="Failed to update shipping profile.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)
