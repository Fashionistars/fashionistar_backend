# apps/admin_backend/order_view.py
from rest_framework import generics, status
from drf_spectacular.utils import extend_schema

from store.models import CartOrder
from store.serializers import CartOrderSerializer
from apps.admin_backend.serializers import AdminProfitSerializer
from apps.common.renderers import CustomJSONRenderer, success_response
 

from decimal import Decimal


class AdminOrderListView(generics.ListAPIView):
    renderer_classes = [CustomJSONRenderer]
    queryset = CartOrder.objects.all()
    serializer_class = CartOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Admin Workflow for Retrieving All Orders:

        1. Admin sends a GET request to the `/admin/orders/` endpoint.
        2. The backend retrieves all orders from the database.
        3. The backend returns the list of orders in the response.
        
        """
        if not self.request.user.is_staff:
            raise PermissionDenied("You do not have permission to view this resource.")
        return super().get_queryset()



class AdminProfitView(generics.GenericAPIView):
    renderer_classes = [CustomJSONRenderer]
    permission_classes = [IsAuthenticated]
    serializer_class = AdminProfitSerializer

    @extend_schema(
        summary="Calculate Admin Profit",
        description="Calculates 10% commission profit from all store orders.",
        responses={200: AdminProfitSerializer}
    )
    def get(self, request, *args, **kwargs):
        """
        Admin Workflow for Retrieving Profit Details:

        1. Admin sends a GET request to the `/admin/profit/` endpoint.
        2. The backend calculates the total amount made from each sale.
        3. The backend returns the profit details in the response.
        """

        if not request.user.is_staff:
            raise PermissionDenied("You do not have permission to view this resource.")

        total_profit = Decimal("0.0")
        orders = CartOrder.objects.all()

        for order in orders:
            total_profit += order.total * Decimal("0.1")  # 10% profit for the company

        return success_response(
            data={"total_profit": total_profit},
            message="Profit calculated successfully."
        )
