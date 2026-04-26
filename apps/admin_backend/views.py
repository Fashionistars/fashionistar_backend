from rest_framework import viewsets, status, parsers
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from apps.admin_backend.models import Brand, Category, Collections
from apps.admin_backend.serializers import (
    BrandSerializer,
    CategorySerializer,
    CollectionsSerializer,
)
from django.http import Http404


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(active=True)
    permission_classes = (AllowAny,)


class CategoryCreateView(generics.CreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [
        AllowAny,
    ]


class BrandListView(generics.ListAPIView):
    serializer_class = BrandSerializer
    queryset = Brand.objects.filter(active=True)
    permission_classes = (AllowAny,)


class CollectionsViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing Collection instances.
    """

    queryset = Collections.objects.all()
    serializer_class = CollectionsSerializer
    permission_classes = [AllowAny]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser)

    def get_object(self):
        slug = self.kwargs.get("slug")
        if not slug:
            return super().get_object()
        try:
            return Collections.objects.get(slug=slug)
        except Collections.DoesNotExist:
            raise Http404

    def create(self, request, *args, **kwargs):
        """
        Create a new Collection instance.

        Args:
            request: The request object containing data for the new instance.

        Returns:
            Response: The response object containing the created instance data.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def update(self, request, *args, **kwargs):
        """
        Update an existing Collection instance.

        Args:
            request: The request object containing data for the update.

        Returns:
            Response: The response object containing the updated instance data.
        """
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """
        Delete an existing Collection instance.

        Args:
            request: The request object.

        Returns:
            Response: The response object indicating the deletion status.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"message": "Image deleted successfully"}, status=status.HTTP_204_NO_CONTENT
        )


class CategoryViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing CATEGORY instances.
    """

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser)

    def get_object(self):
        """
        Override get_object to return the CATEGORY instance based on slug.
        """
        slug = self.kwargs.get("slug")
        try:
            return Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            raise Http404

    def create(self, request, *args, **kwargs):
        """
        Create a new CATEGORY instance.

        Args:
            request: The request object containing data for the new instance.

        Returns:
            Response: The response object containing the created instance data.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        created_instance = Category.objects.get(name=serializer.validated_data["name"])

        # Serialize the full instance
        full_serializer = self.get_serializer(created_instance)
        data = {
            "id": created_instance.id,
            "name": created_instance.name,
            "image": created_instance.image.url if created_instance.image else None,
            "slug": created_instance.slug,
            # 'createdAt': created_instance.createdAt,
            # 'updatedAt': created_instance.updatedAt,
        }
        # Create the response
        headers = self.get_success_headers(full_serializer.data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

        # headers = self.get_success_headers(serializer.data)
        # return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """
        Update an existing CATEGORY instance.

        Args:
            request: The request object containing data for the update.

        Returns:
            Response: The response object containing the updated instance data.
        """
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """
        Delete an existing CATEGORY instance.

        Args:
            request: The request object.

        Returns:
            Response: The response object indicating the deletion status.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"message": "Category deleted successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )


class BrandViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing BRAND instances.
    """

    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [AllowAny]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser)

    def get_object(self):
        slug = self.kwargs.get("slug")
        if not slug:
            return super().get_object()
        try:
            return Brand.objects.get(slug=slug)
        except Brand.DoesNotExist:
            raise Http404

    def create(self, request, *args, **kwargs):
        """
        Create a new BRAND instance.

        Args:
            request: The request object containing data for the new instance.

        Returns:
            Response: The response object containing the created instance data.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def update(self, request, *args, **kwargs):
        """
        Update an existing BRAND instance.

        Args:
            request: The request object containing data for the update.

        Returns:
            Response: The response object containing the updated instance data.
        """
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """
        Delete an existing BRAND instance.

        Args:
            request: The request object.

        Returns:
            Response: The response object indicating the deletion status.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"message": "Image deleted successfully"}, status=status.HTTP_204_NO_CONTENT
        )


# apps/admin_backend/views.py
"""
Admin Backend Domain — Taxonomy Management Views
================================================

Provides administrative tools for managing the core product taxonomy:
Brands, Categories, and Collections. These views are primarily used by the
Fashionistar internal admin dashboard.

Architecture:
  - Viewsets: ModelViewSet is utilized for full CRUD capabilities.
  - Serialization: Standard ModelSerializers with slug-based lookups.
"""

from django.http import Http404
from rest_framework import viewsets, status, parsers, generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response
from apps.admin_backend.models import Brand, Category, Collections
from apps.admin_backend.serializers import (
    BrandSerializer,
    CategorySerializer,
    CollectionsSerializer,
)


# ===========================================================================
# CATEGORY MANAGEMENT
# ===========================================================================


class CategoryListView(generics.ListAPIView):
    """
    GET /api/v1/admin/categories/ — List all active categories.
    """

    serializer_class = CategorySerializer
    queryset = Category.objects.filter(active=True)
    permission_classes = (AllowAny,)
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]


class CategoryCreateView(generics.CreateAPIView):
    """
    POST /api/v1/admin/categories/create/ — Add a new category.
    """

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]


# ===========================================================================
# BRAND MANAGEMENT
# ===========================================================================


class BrandListView(generics.ListAPIView):
    """
    GET /api/v1/admin/brands/ — List active brands.
    """

    serializer_class = BrandSerializer
    queryset = Brand.objects.filter(active=True)
    permission_classes = (AllowAny,)
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]


# ===========================================================================
# COLLECTIONS VIEWSET
# ===========================================================================


class CollectionsViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for Seasonal Collections.

    Endpoints:
      - GET /api/v1/admin/collections/ (List)
      - POST /api/v1/admin/collections/ (Create)
      - GET /api/v1/admin/collections/<slug>/ (Detail)
      - PATCH /api/v1/admin/collections/<slug>/ (Update)
      - DELETE /api/v1/admin/collections/<slug>/ (Destroy)
    """

    queryset = Collections.objects.all()
    serializer_class = CollectionsSerializer
    permission_classes = [AllowAny]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_object(self):
        slug = self.kwargs.get("slug")
        if not slug:
            return super().get_object()
        try:
            return Collections.objects.get(slug=slug)
        except Collections.DoesNotExist:
            raise Http404

    def create(self, request, *args, **kwargs):
        """Create and return success response."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(
            data=serializer.data,
            message="Collection created successfully.",
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        """Update and return success response."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return success_response(
            data=serializer.data, message="Collection updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        """Destroy and return success response."""
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response(
            message="Collection deleted successfully.", status=status.HTTP_200_OK
        )


# ===========================================================================
# CATEGORY VIEWSET
# ===========================================================================


class CategoryViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for Product Categories.
    """

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_object(self):
        slug = self.kwargs.get("slug")
        try:
            return Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            raise Http404

    def create(self, request, *args, **kwargs):
        """Create with custom response payload."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        created_instance = Category.objects.get(name=serializer.validated_data["name"])

        data = {
            "id": created_instance.id,
            "name": created_instance.name,
            "image": created_instance.image.url if created_instance.image else None,
            "slug": created_instance.slug,
        }
        return success_response(
            data=data,
            message="Category created successfully.",
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        """Partial or full update."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return success_response(
            data=serializer.data, message="Category updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        """Soft or hard delete."""
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response(
            message="Category deleted successfully.", status=status.HTTP_200_OK
        )


# ===========================================================================
# BRAND VIEWSET
# ===========================================================================


class BrandViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for Fashion Brands.
    """

    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [AllowAny]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_object(self):
        slug = self.kwargs.get("slug")
        if not slug:
            return super().get_object()
        try:
            return Brand.objects.get(slug=slug)
        except Brand.DoesNotExist:
            raise Http404

    def create(self, request, *args, **kwargs):
        """Create brand."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(
            data=serializer.data,
            message="Brand created successfully.",
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        """Update brand details."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return success_response(
            data=serializer.data, message="Brand updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        """Remove brand profile."""
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response(
            message="Brand deleted successfully.", status=status.HTTP_200_OK
        )
