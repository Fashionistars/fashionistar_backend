from requests import Response

# Restframework Packages
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError, NotFound, APIException
from rest_framework.response import Response
from rest_framework import generics, status


from store.models import *
from store.serializers import *
from admin_backend.serializers import *
 

from decimal import Decimal


class AdminOrderListView(generics.ListAPIView):
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



class AdminProfitView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AdminProfitSerializer


    def get(self, request, *args, **kwargs):
        """
        Admin Workflow for Retrieving Profit Details:

        1. Admin sends a GET request to the `/admin/profit/` endpoint.
        2. The backend calculates the total amount made from each sale.
        3. The backend returns the profit details in the response.

        Example of handling the response in JavaScript:

        fetch('/admin/profit/', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            }
        })
        .then(response => {
            if (response.status === 200) {
                return response.json().then(data => {
                    console.log('Profit Details:', data);
                });
            } else {
                return response.json().then(data => {
                    alert(data.message);
                });
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
        """

        if not request.user.is_staff:
            raise PermissionDenied("You do not have permission to view this resource.")

        total_profit = Decimal(0.0)
        orders = CartOrder.objects.all()

        for order in orders:
            total_profit += order.total * Decimal(0.1)  # 10% profit for the company

        return Response({"total_profit": total_profit}, status=status.HTTP_200_OK)
