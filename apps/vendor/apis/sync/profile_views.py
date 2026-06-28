# apps/vendor/apis/sync/profile_views.py
"""
Vendor Profile API — DRF Sync Views (Generics).

URL prefix: /api/v1/vendor/

Endpoints:
  GET    /api/v1/vendor/profile/     — retrieve my store profile
  PATCH  /api/v1/vendor/profile/     — update profile (scalar fields + M2M collections)
  GET    /api/v1/vendor/setup/       — get onboarding setup state
  POST   /api/v1/vendor/setup/       — create/update first-time vendor setup
  POST   /api/v1/vendor/payout/      — save bank / payout details
  POST   /api/v1/vendor/pin/set/     — set 4-digit transaction PIN
  POST   /api/v1/vendor/pin/verify/  — verify 4-digit PIN before payout
"""

import logging

from rest_framework.generics import GenericAPIView
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsVendor
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response
from apps.vendor.selectors.vendor_selectors import (
    get_vendor_profile_or_none,
    get_vendor_setup_state,
)
from apps.vendor.serializers.profile_serializers import (
    VendorPayoutDetailsSerializer,
    VendorProfileOutputSerializer,
    VendorSetupSerializer,
    VendorProfileUpdateSerializer,
    VendorSetupStateSerializer,
    VendorTransactionPinSerializer,
)
from apps.vendor.services.vendor_provisioning_service import VendorProvisioningService
from apps.vendor.services.vendor_service import VendorService

logger = logging.getLogger(__name__)


class VendorProfileView(GenericAPIView):
    """
    GET  /api/v1/vendor/profile/ — retrieve vendor store profile
    PATCH /api/v1/vendor/profile/ — update store profile
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return VendorProfileUpdateSerializer
        return VendorProfileOutputSerializer

    def get(self, request, *args, **kwargs):
        profile = get_vendor_profile_or_none(request.user)
        if profile is None:
            return error_response(
                message="Vendor setup is required before profile access.",
                code="vendor_setup_required",
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = VendorProfileOutputSerializer(profile)
        return success_response(data=serializer.data)

    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = VendorService.update_profile(
                user=request.user,
                data=serializer.validated_data,
            )
        except Exception as exc:
            logger.exception(
                "VendorProfileView.patch: error for user=%s: %s",
                request.user.pk,
                exc,
            )
            return error_response(
                message="Vendor profile update failed. Ensure vendor setup is complete.",
                code="vendor_setup_required",
                status=status.HTTP_400_BAD_REQUEST,
            )
        output_serializer = VendorProfileOutputSerializer(profile)
        return success_response(
            data=output_serializer.data, message="Profile updated successfully."
        )


class VendorSetupStateView(GenericAPIView):
    """
    GET  /api/v1/vendor/setup/ — retrieve onboarding setup state
    POST /api/v1/vendor/setup/ — create/update the first vendor setup record
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return VendorSetupSerializer
        return VendorSetupStateSerializer

    def get(self, request, *args, **kwargs):
        profile = get_vendor_profile_or_none(request.user)
        if profile is None:
            # Vendor registered but profile not yet provisioned
            data = {
                "current_step": 1,
                "completion_percentage": 0,
                "profile_complete": False,
                "bank_details": False,
                "id_verified": False,
                "first_product": False,
                "onboarding_done": False,
            }
            return success_response(data=data)

        setup = get_vendor_setup_state(profile)
        if setup is None:
            data = {
                "current_step": 1,
                "completion_percentage": 0,
                "profile_complete": False,
                "bank_details": False,
                "id_verified": False,
                "first_product": False,
                "onboarding_done": False,
            }
            return success_response(data=data)

        serializer = VendorSetupStateSerializer(setup)
        return success_response(data=serializer.data)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = VendorProvisioningService.provision(
            request.user,
            data=serializer.validated_data,
        )
        setup = get_vendor_setup_state(profile)

        data = {
            "profile": VendorProfileOutputSerializer(profile).data,
            "setup_state": (
                VendorSetupStateSerializer(setup).data if setup is not None else None
            ),
        }
        return success_response(
            data=data,
            message="Vendor setup completed successfully.",
            status=status.HTTP_201_CREATED,
        )


class VendorPayoutView(GenericAPIView):
    """
    POST /api/v1/vendor/payout/ — save bank / payout account details
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorPayoutDetailsSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payout = VendorService.save_payout_details(
                user=request.user,
                data=dict(serializer.validated_data),
            )
        except Exception as exc:
            logger.exception(
                "VendorPayoutView.post: error for user=%s: %s",
                request.user.pk,
                exc,
            )
            return error_response(
                message="Payout details save failed. Ensure vendor setup is complete.",
                code="vendor_setup_required",
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = {
            "bank_name": payout.bank_name,
            "account_name": payout.account_name,
            "account_last4": payout.account_last4,
            "is_verified": payout.is_verified,
        }
        return success_response(
            data=data,
            message="Payout details saved successfully.",
            status=status.HTTP_201_CREATED,
        )


class VendorSetPinView(GenericAPIView):
    """
    POST /api/v1/vendor/pin/set/ — set 4-digit payout confirmation PIN
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorTransactionPinSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            VendorService.set_transaction_pin(
                user=request.user,
                raw_pin=serializer.validated_data["pin"],
            )
        except ValueError as exc:
            return error_response(
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception(
                "VendorSetPinView.post: error for user=%s: %s", request.user.pk, exc
            )
            return error_response(
                message="PIN update failed.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        return success_response(message="Transaction PIN set successfully.")


class VendorVerifyPinView(GenericAPIView):
    """
    POST /api/v1/vendor/pin/verify/ — verify payout PIN before withdrawal
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorTransactionPinSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_valid = VendorService.verify_transaction_pin(
            user=request.user,
            raw_pin=serializer.validated_data["pin"],
        )
        if not is_valid:
            return error_response(
                message="Invalid PIN.",
                code="invalid_pin",
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return success_response(message="PIN verified successfully.")


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC VENDOR ENDPOINTS (AllowAny — no authentication required)
# ══════════════════════════════════════════════════════════════════════════════


class PublicVendorListView(GenericAPIView):
    """
    GET /api/v1/vendor/public/
    Public listing of active vendors for the home/vendors marketplace page.

    Permissions: AllowAny (no auth required — publicly browsable).
    Filters (query params):
      ?is_featured=true    — featured vendors only
      ?city=Lagos          — filter by city
      ?search=bespoke      — search store_name / tagline
      ?limit=24            — page size (default 24, max 100)
      ?offset=0            — pagination offset

    Response: { status, count, data: [VendorCard...] }
    """

    permission_classes  = [AllowAny]
    renderer_classes    = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request, *args, **kwargs):
        from apps.vendor.models import VendorProfile
        from django.db.models import Q

        qs = (
            VendorProfile.objects
            .filter(is_active=True)
            .only(
                "id", "store_name", "store_slug", "tagline", "description",
                "logo_url", "cover_url", "city", "state", "country",
                "is_verified", "is_featured", "average_rating", "review_count",
                "total_products", "total_sales",
            )
            .order_by("-is_featured", "-average_rating", "-total_sales")
        )

        # ── Filters ──────────────────────────────────────────────────────────
        is_featured = request.query_params.get("is_featured")
        if is_featured in ("true", "1"):
            qs = qs.filter(is_featured=True)

        city = request.query_params.get("city", "").strip()
        if city:
            qs = qs.filter(city__icontains=city)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(store_name__icontains=search) | Q(tagline__icontains=search)
            )

        # ── Pagination ───────────────────────────────────────────────────────
        try:
            limit  = min(int(request.query_params.get("limit",  24)), 100)
            offset = max(int(request.query_params.get("offset",  0)),  0)
        except (ValueError, TypeError):
            limit, offset = 24, 0

        total = qs.count()
        page  = qs[offset : offset + limit]

        data = [
            {
                "id":             str(v.id),
                "store_name":     v.store_name,
                "store_slug":     v.store_slug,
                "tagline":        v.tagline,
                "description":    v.description,
                "logo_url":       str(v.logo_url) if v.logo_url else "",
                "cover_url":      str(v.cover_url) if v.cover_url else "",
                "city":           v.city,
                "state":          v.state,
                "country":        v.country,
                "is_verified":    v.is_verified,
                "is_featured":    v.is_featured,
                "average_rating": float(v.average_rating),
                "review_count":   v.review_count,
                "total_products": v.total_products,
                "total_sales":    v.total_sales,
            }
            for v in page
        ]

        return success_response(data={"count": total, "results": data})


class PublicVendorDetailView(GenericAPIView):
    """
    GET /api/v1/vendor/public/{store_slug}/
    Public vendor profile detail for the /vendors/[slug] page.

    Permissions: AllowAny.
    Returns full vendor profile plus top 12 products.
    """

    permission_classes  = [AllowAny]
    renderer_classes    = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request, store_slug: str, *args, **kwargs):
        from apps.vendor.models import VendorProfile

        try:
            vendor = (
                VendorProfile.objects
                .prefetch_related("collections")
                .get(store_slug=store_slug, is_active=True)
            )
        except VendorProfile.DoesNotExist:
            return error_response(
                message="Vendor store not found.",
                code="not_found",
                status=status.HTTP_404_NOT_FOUND,
            )

        # Top products (up to 12 most recent published)
        products_qs = (
            vendor.vendor_products
            .filter(status="published")
            .order_by("-date")
            .values("pid", "title", "price", "old_price", "stock_qty")[:12]
        )

        data = {
            "id":             str(vendor.id),
            "store_name":     vendor.store_name,
            "store_slug":     vendor.store_slug,
            "tagline":        vendor.tagline,
            "description":    vendor.description,
            "logo_url":       str(vendor.logo_url) if vendor.logo_url else "",
            "cover_url":      str(vendor.cover_url) if vendor.cover_url else "",
            "city":           vendor.city,
            "state":          vendor.state,
            "country":        vendor.country,
            "whatsapp":       vendor.whatsapp,
            "instagram_url":  vendor.instagram_url,
            "tiktok_url":     vendor.tiktok_url,
            "twitter_url":    vendor.twitter_url,
            "website_url":    vendor.website_url,
            "is_verified":    vendor.is_verified,
            "is_featured":    vendor.is_featured,
            "average_rating": float(vendor.average_rating),
            "review_count":   vendor.review_count,
            "total_products": vendor.total_products,
            "total_sales":    vendor.total_sales,
            "collections": [
                {"id": str(c.id), "title": c.title, "slug": c.slug}
                for c in vendor.collections.all()
            ],
            "products": list(products_qs),
        }

        return success_response(data=data)
