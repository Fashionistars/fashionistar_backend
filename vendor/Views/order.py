# vendor/Views/order.py

import logging

from django.db import transaction # Don't forget to import transaction

# ... (other imports)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework import filters, generics, status

from rest_framework.permissions import IsAuthenticated
from vendor.permissions import IsVendor, IsOwner

# Import custom components from vendor app (adjusted for correct paths)
from vendor.serializerss.order import  (
    VendorOrderListSerializer,
    VendorOrderDetailSerializer,
    OrderActionSerializer
)

from vendor.filters import OrderFilter # Import our new order filter
from vendor.pagination import VendorCatalogPagination 

from vendor.models import Vendor
from store.models import CartOrder


# Imports for Swagger Schema Documentation
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


application_logger = logging.getLogger('application')




class VendorOrderListView(generics.ListAPIView):
    """
    API endpoint for an authenticated vendor to view their orders.

    Provides a paginated, filterable, and searchable list of orders.
    *   **Filtering:** by `order_status` (e.g., `?order_status=Pending`).
    *   **Searching:** by `oid` (e.g., `?search=CO123abc`).
    """
    serializer_class = VendorOrderListSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    pagination_class = VendorCatalogPagination # Re-using the pagination class
    
    # Setup filtering and searching
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrderFilter
    search_fields = ['oid']
    ordering_fields = ['date']

    def get_queryset(self):
        """
        Ensures the queryset returns only orders belonging to the authenticated vendor,
        optimizing with `select_related` to pre-fetch customer data and reduce database hits.
        """
        try:
            vendor = self.request.user.vendor_profile
            # Use `select_related` for performance. It fetches the related 'buyer' and 'profile'
            # in the same database query, preventing N+1 problems.
            return vendor.cartorder_vendor.select_related('buyer__profile').order_by('-date')
        except Vendor.DoesNotExist:
            application_logger.critical(f"CRITICAL: User {self.request.user.email} has 'vendor' role but no Vendor profile.")
            return CartOrder.objects.none()





class VendorOrderDetailView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for a vendor to view a single order's details and perform actions.

    *   **GET:** Retrieves detailed information about a specific order.
    *   **PATCH:** Updates the order's status (e.g., accept or reject an order).
    """
    permission_classes = [IsAuthenticated, IsVendor, IsOwner]
    lookup_field = 'oid'
    lookup_url_kwarg = 'order_oid'

    def get_serializer_class(self):
        """
        Dynamically determine which serializer to use based on the request method.
        - `GET` requests use the detailed serializer.
        - `PATCH` requests use the action validation serializer.
        """
        if self.request.method == 'PATCH':
            return OrderActionSerializer
        return VendorOrderDetailSerializer

    def get_queryset(self):
        """
        Returns an optimized queryset for a single order.

        Uses `prefetch_related` to efficiently load all related order items and their
        associated products in a minimal number of queries, which is essential for performance.
        """
        try:
            vendor = self.request.user.vendor_profile
            # `prefetch_related` is crucial here. It fetches all related 'cart_order' items
            # and their 'product' details in just two extra queries, regardless of how many items are in the order.
            return vendor.cartorder_vendor.prefetch_related('cart_order__product')
        except Vendor.DoesNotExist:
            application_logger.critical(f"CRITICAL: User {self.request.user.email} has 'vendor' role but no Vendor profile.")
            return CartOrder.objects.none()

    @swagger_auto_schema(
        operation_summary="Perform Action on Order (Accept/Reject)",
        request_body=OrderActionSerializer,
        responses={
            200: openapi.Response("Action performed successfully.", schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'order_status': openapi.Schema(type=openapi.TYPE_STRING)
                }
            )),
            400: "Bad Request - Invalid action provided."
        }
    )
    def patch(self, request, *args, **kwargs):
        """
        Handles the 'Accept' or 'Reject' action for an order.
        """
        user = request.user
        order = self.get_object() # This also runs the IsOwner permission check
        application_logger.info(f"Action attempt on Order OID '{order.oid}' by user '{user.identifying_info}'.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']

        try:
            with transaction.atomic():
                if action == 'accept':
                    # Update order status based on business logic.
                    # This could be 'Processing', 'Ready to deliver', etc.
                    order.order_status = "Processing" # Example status
                    message = "Order accepted successfully!"
                elif action == 'reject':
                    order.order_status = "Cancelled" # Example status
                    message = "Order rejected by vendor."
                
                order.save()

            application_logger.info(f"Action '{action}' on Order OID '{order.oid}' by vendor '{user.vendor_profile.name}' was successful.")
            return Response({
                "message": message,
                "order_status": order.order_status
            }, status=status.HTTP_200_OK)

        except Exception as e:
            application_logger.critical(f"An unexpected error occurred during action on Order OID '{order.oid}': {str(e)}")
            return Response({"error": "An unexpected server error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        








