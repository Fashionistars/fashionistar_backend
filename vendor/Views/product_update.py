# vendor/Views/product_update.py

import logging

# ... (other imports)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.parsers import MultiPartParser, FormParser

from rest_framework import filters, generics
from rest_framework.permissions import IsAuthenticated

# Import custom components from vendor app (adjusted for correct paths)
from vendor.serializerss.product_update import ProductUpdateSerializer1
from vendor.filters import ProductFilter
from vendor.pagination import VendorCatalogPagination
from vendor.models import Vendor
from store.models import Product


# Imports for Swagger Schema Documentation
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi



# Import the IsOwner permission
from vendor.permissions import IsVendor, IsOwner

application_logger = logging.getLogger('application')



class ProductUpdateAPIView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for a vendor to retrieve (for editing) and update their own product.

    *   **URL:** `/api/vendor/product/update/<product_pid>/`
    *   **Methods:** `GET`, `PUT`, `PATCH`
    *   **Authentication:** `IsAuthenticated`
    *   **Permissions:** `IsVendor`, `IsOwner` (ensures only the product's creator can edit)
    *   **Lookup:** Uses the product's public ID (`pid`) from the URL.
    """
    queryset = Product.objects.all()
    serializer_class = ProductUpdateSerializer1
    # parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated, IsVendor, IsOwner]
    lookup_field = 'pid'
    lookup_url_kwarg = 'product_pid'  # Explicitly name the URL kwarg for clarity

    @swagger_auto_schema(
        operation_summary="Retrieve or Update a Vendor's Product",
        operation_description="GET: Fetches a single product's details for editing.\n\nPUT/PATCH: Updates a product's details. All nested objects (gallery, sizes, etc.) will be replaced with the data provided.",
        responses={
            200: openapi.Response("Product details updated/retrieved successfully", ProductUpdateSerializer1),
            400: "Bad Request - Invalid data provided",
            403: "Permission Denied - You are not the owner of this product",
            404: "Not Found - Product with the specified PID does not exist",
            500: "Internal Server Error"
        }
    )
    def update(self, request, *args, **kwargs):
        """
        Wraps the update logic in a database transaction.

        This ensures that the update to the product and all its related nested objects
        is an atomic operation. If any part fails, the entire transaction is rolled back,
        preventing data corruption.
        """
        user = request.user
        # The `get_object` call implicitly runs DRF's permission checks, including our IsOwner class.
        product = self.get_object()
        application_logger.info(f"Product update attempt by user '{user.identifying_info}' for product PID '{product.pid}'.")

        try:
            # Wrap the call to the parent's update method in a transaction.
            with transaction.atomic():
                response = super().update(request, *args, **kwargs)

            application_logger.info(f"Product PID '{product.pid}' updated successfully by vendor '{user.vendor_profile.name}'.")
            return response

        except ValidationError as e:
            application_logger.error(f"Validation error during product update for PID '{product.pid}': {e.detail}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            application_logger.critical(f"An unexpected error occurred during product update for PID '{product.pid}': {str(e)}")
            return Response({"error": "An unexpected server error occurred. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # The retrieve (GET) method is handled automatically by RetrieveUpdateAPIView
    # and is already protected by our permission classes.









