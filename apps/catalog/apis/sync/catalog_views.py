from rest_framework import generics, parsers

from apps.admin_backend.models import Brand, Category, Collections
from apps.catalog.permissions import IsCatalogStaffOrReadOnly
from apps.catalog.selectors import CatalogSelector
from apps.catalog.serializers import (
    CatalogBrandSerializer,
    CatalogCategorySerializer,
    CatalogCollectionSerializer,
)
from apps.catalog.services import CatalogAuditService


class CatalogMutationAuditMixin:
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


class CatalogCategoryListCreateView(CatalogMutationAuditMixin, generics.ListCreateAPIView):
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
    serializer_class = CatalogCategorySerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    lookup_field = "slug"
    resource_type = "Category"

    def get_queryset(self):
        return Category.objects.all()


class CatalogBrandListCreateView(CatalogMutationAuditMixin, generics.ListCreateAPIView):
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
    serializer_class = CatalogBrandSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    lookup_field = "slug"
    resource_type = "Brand"

    def get_queryset(self):
        return Brand.objects.all()


class CatalogCollectionListCreateView(CatalogMutationAuditMixin, generics.ListCreateAPIView):
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
    serializer_class = CatalogCollectionSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    lookup_field = "slug"
    resource_type = "Collection"

    def get_queryset(self):
        return Collections.objects.all()
