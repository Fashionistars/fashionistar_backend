# apps/cart/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.admin_backend.permissions import IsAdminUser
from apps.cart.models.cart import Cart
from apps.cart.admin_backend.services import admin_clear_cart

logger = logging.getLogger(__name__)

class AdminClearCartView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, cart_id):
        try:
            cart = Cart.objects.get(id=cart_id)
        except Cart.DoesNotExist:
            return Response({"status": "error", "message": "Cart not found."}, status=status.HTTP_404_NOT_FOUND)
            
        try:
            admin_clear_cart(cart_id=cart_id, admin_user=request.user)
            return Response({"status": "success", "message": "Cart cleared successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
