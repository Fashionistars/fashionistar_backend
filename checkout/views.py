# Django Packages
from django.shortcuts import get_object_or_404, redirect
from django.core.exceptions import ObjectDoesNotExist

# Restframework Packages
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import ValidationError, NotFound, APIException
from rest_framework import generics, status

# Serializers
from store.serializers import  CartOrderSerializer
from customer.serializers import DeliveryContactSerializer, ShippingAddressSerializer
from ShopCart.serializers import CartSerializer
from .utils import calculate_shipping_amount, calculate_service_fee
from decimal import Decimal

# Models
from store.models import CartOrderItem,  Product, CartOrder,Coupon
from ShopCart.models import Cart
from customer.models import DeliveryContact, ShippingAddress

# Others Packages
from decimal import Decimal
import requests




class CheckoutView(generics.RetrieveAPIView):
    """
    Retrieve the cart details for the checkout process.
    """
    serializer_class = CartOrderSerializer
    lookup_field = 'cart_id'

    def get_object(self):
        cart_id = self.kwargs['cart_id']
        cart_items = Cart.objects.filter(cart_id=cart_id)
        if not cart_items.exists():
            raise ValidationError("Cart not found")
        return cart_items

    def get(self, request, *args, **kwargs):
        """
        Get the cart details and calculate the subtotal, service fee, shipping amount, and total.
        """
        cart_items = self.get_object()
        subtotal = sum(item.sub_total for item in cart_items)
        service_fee = calculate_service_fee(subtotal)
        shipping_amount = Decimal('0.00')  # Initial value, to be updated based on shipping address

        data = {
            'cart_items': CartSerializer(cart_items, many=True).data,
            'subtotal': subtotal,
            'service_fee': service_fee,
            'shipping_amount': shipping_amount,
            'total': subtotal + service_fee + shipping_amount
        }
        return Response(data, status=status.HTTP_200_OK)



class CalculateShippingView(APIView):
    """
    Calculate the shipping amount based on the provided shipping address.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        shipping_address = request.data.get('shipping_address')
        if not shipping_address:
            return Response({"error": "Shipping address is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        shipping_amount = calculate_shipping_amount(shipping_address)
        return Response({"shipping_amount": shipping_amount}, status=status.HTTP_200_OK)



class CalculateServiceFeeView(APIView):
    """
    Calculate the service fee based on the provided subtotal.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        subtotal = request.data.get('subtotal')
        if subtotal is None:
            return Response({"error": "Subtotal is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        subtotal = Decimal(subtotal)
        service_fee = calculate_service_fee(subtotal)
        return Response({"service_fee": service_fee}, status=status.HTTP_200_OK)




class DeliveryContactListCreateView(generics.ListCreateAPIView):
    """
    List and create delivery contacts.
    """
    queryset = DeliveryContact.objects.all()
    serializer_class = DeliveryContactSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Handle the creation of a new delivery contact.
        """
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)




class DeliveryContactDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a delivery contact.
    """
    queryset = DeliveryContact.objects.all()
    serializer_class = DeliveryContactSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        """
        Retrieve a delivery contact by its primary key.
        """
        pk = self.kwargs['pk']
        try:
            return get_object_or_404(DeliveryContact, pk=pk)
        except ObjectDoesNotExist as e:
            raise NotFound(f"Delivery contact not found: {str(e)}")
        except Exception as e:
            raise APIException(f"An error occurred: {str(e)}")



class ShippingAddressListCreateView(generics.ListCreateAPIView):
    """
    List and create shipping addresses.
    """
    queryset = ShippingAddress.objects.all()
    serializer_class = ShippingAddressSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Handle the creation of a new shipping address.
        """
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



class ShippingAddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a shipping address.
    """
    queryset = ShippingAddress.objects.all()
    serializer_class = ShippingAddressSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        """
        Retrieve a shipping address by its primary key.
        """
        pk = self.kwargs['pk']
        try:
            return get_object_or_404(ShippingAddress, pk=pk)
        except ObjectDoesNotExist as e:
            raise NotFound(f"Shipping address not found: {str(e)}")
        except Exception as e:
            raise APIException(f"An error occurred: {str(e)}")