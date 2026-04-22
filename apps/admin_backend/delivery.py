# Django Packages
from django.shortcuts import get_object_or_404, redirect
from django.conf import settings

# Restframework Packages
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError, NotFound, APIException
from rest_framework import generics, status

# Models
from store.models import CartOrder, CartOrderItem



class DeliveryStatusUpdateView(APIView):
    def post(self, request, order_id, *args, **kwargs):
        order = get_object_or_404(CartOrder, id=order_id)
        delivery_status = request.data.get('delivery_status')
        tracking_id = request.data.get('tracking_id')
        if delivery_status:
            order.delivery_status = delivery_status
        if tracking_id:
            order.tracking_id = tracking_id
        order.save()
        return Response({"message": "Delivery status updated"}, status=status.HTTP_200_OK)




