# vendor/Views/product_list.py

import logging

# ... (other imports)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics
from rest_framework.permissions import IsAuthenticated

# Import custom components from vendor app (adjusted for correct paths)
from vendor.serializerss.product_list import VendorProductListSerializer
from vendor.permissions import IsVendor
from vendor.filters import ProductFilter
from vendor.pagination import VendorCatalogPagination
from vendor.models import Vendor
from store.models import Product



application_logger = logging.getLogger('application')


class VendorProductListView(generics.ListAPIView):
    """
    API endpoint for an authenticated vendor to view their own product catalog.

    Provides a paginated and filterable list of products belonging to the vendor.
    Supports filtering by product status and category name.

    *   **URL:** `/api/vendor/catalog/`
    *   **Method:** `GET`
    *   **Authentication:** `IsAuthenticated`
    *   **Permissions:** `IsVendor`
    *   **Query Parameters for Filtering:**
        *   `status`: (e.g., 'published', 'draft')
        *   `category`: (e.g., 'Bags', 'Clothing')
    *   **Query Parameters for Pagination:**
        *   `page`: Page number (e.g., 2)
        *   `page_size`: Number of items per page (e.g., 5)
    """
    serializer_class = VendorProductListSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    
    # Setup pagination and filtering
    pagination_class = VendorCatalogPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ProductFilter
    ordering_fields = ['date', 'price', 'title'] # Fields the frontend can use for sorting

    def get_queryset(self):
        """
        This method is overridden to ensure that the queryset is filtered to
        return only the products that belong to the currently authenticated vendor.
        """
        try:
            # `request.user.vendor_profile` is reliable here because the `IsVendor`
            # permission has already verified the user is a vendor.
            vendor = self.request.user.vendor_profile
            
            # Order by the most recently created products first.
            return Product.objects.filter(vendor=vendor).order_by('-date')
        
        except Vendor.DoesNotExist:
            # This is a critical state error; a user with role 'vendor' MUST have a profile.
            # Log it with high severity.
            application_logger.critical(f"CRITICAL: User {self.request.user.email} has 'vendor' role but no Vendor profile.")
            # Return an empty queryset to prevent leaking data and show an empty list.
            return Product.objects.none()
        except Exception as e:
            # Catch any other unexpected errors during queryset retrieval.
            application_logger.error(f"An unexpected error occurred while fetching product list for vendor {self.request.user.email}: {str(e)}")
            # Return an empty queryset.
            return Product.objects.none()