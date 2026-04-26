# apps/catalog/apis/sync/catalog_views.py
"""
Catalog Domain — Product Taxonomy & Organizational Views
========================================================

Handles the public-facing and administrative views for Brands, Categories, 
and Collections. 

Architecture:
  - Selectors: used for optimized read queries (CatalogSelector).
  - Services: used for audit-logged write operations (CatalogAuditService).
  - Mixins: CatalogMutationAuditMixin ensures every change is logged for internal tracking.

Security:
  - GET methods: AllowAny (via IsCatalogStaffOrReadOnly).
  - POST/PATCH/PUT: Restricted to Catalog Staff / Admins.
"""

from rest_framework import generics, parsers, status
from rest_framework.renderers import BrowsableAPIRenderer

from apps.admin_backend.models import Brand, Category, Collections
from apps.catalog.permissions import IsCatalogStaffOrReadOnly
from apps.catalog.selectors import CatalogSelector
from apps.catalog.serializers import (
    CatalogBrandSerializer,
    CatalogCategorySerializer,
    CatalogCollectionSerializer,
)
from apps.catalog.services import CatalogAuditService
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response


# ===========================================================================
# AUDIT LOGGING MIXIN
# ===========================================================================


class CatalogMutationAuditMixin:
    """
    Hooks into DRF's perform_create and perform_update to log changes.
    """
    resource_type = "Catalog"

    def perform_create(self, serializer):
        instance = serializer.save()
        CatalogAuditService.log_mutation(
            request=self.request,
            action=f"{self.resource_type} created",
            resource_type=self.resource_type,
            resource_id=instance.pk,
            new_values=serializer.data,
        )

    def perform_update(self, serializer):
        old_values = self.get_serializer(self.get_object()).data
        instance = serializer.save()
        CatalogAuditService.log_mutation(
            request=self.request,
            action=f"{self.resource_type} updated",
            resource_type=self.resource_type,
            resource_id=instance.pk,
            old_values=dict(old_values),
            new_values=serializer.data,
        )


# ===========================================================================
# CATEGORY MANAGEMENT
# ===========================================================================


class CatalogCategoryListCreateView(CatalogMutationAuditMixin, generics.ListCreateAPIView):
    """
    GET /api/v1/catalog/categories/ — Public list of all categories.
    POST /api/v1/catalog/categories/ — Staff-only creation.

    Flow:
      1. Retrieve optimized category tree for GET.
      2. Validate and audit-log creation for POST.

    Status Codes:
      200 OK: Returns category list.
      201 Created: New category added.
    """
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = CatalogCategorySerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    pagination_class = None
    resource_type = "Category"

    def get_queryset(self):
        if self.request.method == "GET":
            return CatalogSelector.categories()
        return Category.objects.all().order_by("name")


class CatalogCategoryDetailView(CatalogMutationAuditMixin, generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/catalog/categories/<slug>/ — View specific category details.
    PATCH /api/v1/catalog/categories/<slug>/ — Staff-only update.

    Status Codes:
      200 OK: Details retrieved or updated.
      404 Not Found: Category does not exist.
    """
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = CatalogCategorySerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    lookup_field = "slug"
    resource_type = "Category"

    def get_queryset(self):
        return Category.objects.all()


# ===========================================================================
# BRAND MANAGEMENT
# ===========================================================================


class CatalogBrandListCreateView(CatalogMutationAuditMixin, generics.ListCreateAPIView):
    """
    GET /api/v1/catalog/brands/ — Public list of brands.
    POST /api/v1/catalog/brands/ — Staff-only creation.

    Status Codes:
      200 OK: Brand list returned.
      201 Created: Brand profile created.
    """
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = CatalogBrandSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    pagination_class = None
    resource_type = "Brand"

    def get_queryset(self):
        if self.request.method == "GET":
            return CatalogSelector.brands()
        return Brand.objects.all().order_by("title")


class CatalogBrandDetailView(CatalogMutationAuditMixin, generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/catalog/brands/<slug>/ — Brand details.
    PATCH /api/v1/catalog/brands/<slug>/ — Admin update.
    """
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = CatalogBrandSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    lookup_field = "slug"
    resource_type = "Brand"

    def get_queryset(self):
        return Brand.objects.all()


# ===========================================================================
# COLLECTION MANAGEMENT
# ===========================================================================


class CatalogCollectionListCreateView(CatalogMutationAuditMixin, generics.ListCreateAPIView):
    """
    GET /api/v1/catalog/collections/ — Seasonal or thematic product groupings.
    """
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = CatalogCollectionSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    pagination_class = None
    resource_type = "Collection"

    def get_queryset(self):
        if self.request.method == "GET":
            return CatalogSelector.collections()
        return Collections.objects.all().order_by("-created_at")


class CatalogCollectionDetailView(CatalogMutationAuditMixin, generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/catalog/collections/<slug>/ — View items in collection.
    """
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = CatalogCollectionSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    lookup_field = "slug"
    resource_type = "Collection"

    def get_queryset(self):
        return Collections.objects.all()

