# vendor/Views/product_delete.py

import logging

# ... (other imports)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.parsers import MultiPartParser, FormParser

from rest_framework.response import Response
from rest_framework import filters, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

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




class ProductDeleteAPIView(generics.DestroyAPIView):
    """
    API endpoint for a vendor to delete their own product.

    This is a destructive action and cannot be undone. The IsOwner permission
    ensures that only the vendor who created the product can delete it.

    *   **URL:** `/api/vendor/product/delete/<product_pid>/`
    *   **Method:** `DELETE`
    *   **Authentication:** `IsAuthenticated`
    *   **Permissions:** `IsVendor`, `IsOwner`
    *   **Lookup:** Uses the product's public ID (`pid`) from the URL.
    """
    queryset = Product.objects.all()
    permission_classes = [IsAuthenticated, IsVendor, IsOwner]
    lookup_field = 'pid'
    lookup_url_kwarg = 'product_pid'

    @swagger_auto_schema(
        operation_summary="Delete a Vendor's Product",
        operation_description="Permanently deletes a product and all its associated data (gallery, sizes, etc.). This action cannot be undone.",
        responses={
            204: "No Content - Product deleted successfully",
            403: "Permission Denied - You are not the owner of this product",
            404: "Not Found - Product with the specified PID does not exist",
            500: "Internal Server Error"
        }
    )
    def destroy(self, request, *args, **kwargs):
        """
        Overrides the default destroy method to add detailed logging and error handling.
        """
        user = request.user
        try:
            # The get_object method will retrieve the product and implicitly run
            # the IsOwner permission check, raising a PermissionDenied or NotFound
            # error if the check fails, which is handled by DRF's exception handler.
            instance = self.get_object()
            product_title = instance.title  # Capture title for logging before deletion
            vendor_name = user.vendor_profile.name

            application_logger.info(f"Product deletion attempt by vendor '{vendor_name}' for product '{product_title}' (PID: {instance.pid}).")

            # The actual deletion is handled by the parent class.
            self.perform_destroy(instance)

            application_logger.warning(f"DELETION SUCCESSFUL: Product '{product_title}' (PID: {instance.pid}) was permanently deleted by vendor '{vendor_name}'.")
            
            # A successful DELETE should return 204 No Content.
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            # This will catch any unexpected database errors during deletion.
            product_pid = self.kwargs.get('product_pid')
            application_logger.critical(f"An unexpected error occurred during product deletion for PID '{product_pid}' by user '{user.identifying_info}': {str(e)}")
            return Response({"error": "An unexpected server error occurred while trying to delete the product."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        






        