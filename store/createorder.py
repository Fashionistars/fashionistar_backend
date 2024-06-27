# Django Packages
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404

# Restframework Packages
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError, NotFound, APIException
from rest_framework import generics, status

# Serializers
from store.serializers import  ProductSerializer,  CartOrderSerializer, ReviewSerializer, ConfigSettingsSerializer
from customer.serializers import DeliveryContactSerializer, ShippingAddressSerializer
from ShopCart.serializers import CartSerializer
from .utils import calculate_shipping_amount, calculate_service_fee
from decimal import Decimal

# Models
from userauths.models import User, Profile
from store.models import CartOrderItem,  Notification, Product, CartOrder,  Review, Coupon
from addon.models import ConfigSettings
from ShopCart.models import Cart
from customer.models import DeliveryContact, ShippingAddress

# Others Packages
from decimal import Decimal
import stripe
import requests




class CreateOrderView(generics.CreateAPIView):
    serializer_class = CartOrderSerializer
    queryset = CartOrder.objects.all()
    permission_classes = (IsAuthenticated,)

    def create(self, request, *args, **kwargs):
        """
        Frontend Workflow for Creating an Order:

        1. User clicks on the 'Create Order' button.
        2. The frontend sends a POST request to the `/create-order/` endpoint with the following payload:
            {
                "full_name": "User's full name",
                "email": "User's email",
                "mobile": "User's mobile number",
                "address": "User's address",
                "city": "User's city",
                "state": "User's state",
                "country": "User's country",
                "cart_id": "Cart ID",
                "user_id": "User ID",
                "transaction_password": "User's transaction password"
            }
        3. The backend checks if the user's transaction password is set:
            a. If not set, it responds with a 302 status code and a `redirect_url` to prompt the user to set the transaction password.
            b. If set, it validates the provided transaction password. If invalid, it responds with an error message.
        4. If the transaction password is valid, the backend proceeds with the following steps:
            a. Validates the request data.
            b. Fetches the user and cart items.
            c. Checks if the user's wallet balance is sufficient to cover the order total.
            d. Creates the order and order items.
            e. Updates the user's wallet balance.
            f. Deletes the cart items.
            g. Responds with a success message and the order ID.

        Frontend should handle:
        1. Checking the response status code.
        2. If the status code is 302, redirect the user to the URL provided in the `redirect_url` field.
        3. If the status code is 201, show a success message.
        4. If the status code is 400, show the error message.

        Example of handling the response in JavaScript:

        fetch('/create-order/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            },
            body: JSON.stringify(orderData)
        })
        .then(response => {
            if (response.status === 302) {
                return response.json().then(data => {
                    window.location.href = data.redirect_url;
                });
            } else if (response.status === 201) {
                return response.json().then(data => {
                    alert('Order Created Successfully!');
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
        
        """
        Step-by-step process for creating an order:
        1. Validate transaction password:
            a. Retrieve the user's profile.
            b. Check if the transaction password is set. If not, return a response to prompt setting it.
            c. Validate the provided transaction password. If invalid, return an error response.
        
        2. Extract and validate request data:
            a. Ensure all required fields are present in the payload.
            b. Extract data from the payload for order creation.
        
        3. Fetch user:
            a. Retrieve the user object based on the provided user_id.
        
        4. Retrieve cart items:
            a. Fetch cart items associated with the provided cart_id.
            b. Ensure cart items exist, otherwise, return an error response.
        
        5. Initialize totals:
            a. Initialize variables to keep track of total costs (shipping, service fee, subtotal, etc.).
        
        6. Check user's wallet balance:
            a. Ensure the user's wallet balance is sufficient to cover the order total.
            b. If insufficient, return a permission denied response.
        
        7. Create order and order items:
            a. Create a CartOrder instance.
            b. For each cart item, create a CartOrderItem instance.
            c. Aggregate totals (shipping, service fee, subtotal, etc.).
            d. Add vendor to the order.
        
        8. Update and save order:
            a. Update the CartOrder instance with aggregated totals.
            b. Save the CartOrder instance.
        
        9. Deduct order total from user's wallet balance:
            a. Deduct the total cost of the order from the user's wallet balance.
            b. Save the updated user profile.
        
        10. Delete cart items:
            a. Delete the cart items after the order is created.
        
        11. Return success response:
            a. Return a response indicating the order was created successfully, along with the order ID.
        """

        # Validate transaction password
        profile = Profile.objects.get(user=request.user)
        if not profile.transaction_password:
            # Custom response to prompt setting a transaction password
            return Response(
                {
                    "message": "Transaction password not set. Please set it first.",
                    "redirect_url": "/set-transaction-password/"
                },
                status=status.HTTP_302_FOUND  # Using 302 status code to indicate redirection
            )

        password = request.data.get('transaction_password')
        if not profile.check_transaction_password(password):
            return Response({"message": "Invalid transaction password."}, status=status.HTTP_400_BAD_REQUEST)

        # Proceed with order creation if password is valid
        payload = request.data

        # Extract and validate request data
        required_fields = ['full_name', 'email', 'mobile', 'address', 'city', 'state', 'country', 'cart_id', 'user_id']
        for field in required_fields:
            if field not in payload:
                raise ValidationError({field: "This field is required."})

        full_name = payload['full_name']
        email = payload['email']
        mobile = payload['mobile']
        address = payload['address']
        city = payload['city']
        state = payload['state']
        country = payload['country']
        cart_id = payload['cart_id']
        user_id = payload['user_id']

        # Fetch user if user_id is provided
        try:
            user = get_object_or_404(User, id=user_id)
        except Exception as e:
            raise NotFound(f"User not found: {str(e)}")

        # Retrieve cart items
        cart_items = Cart.objects.filter(cart_id=cart_id)
        if not cart_items.exists():
            raise NotFound("Cart not found or empty")

        # Initialize totals
        total_shipping = Decimal(0.0)
        total_service_fee = Decimal(0.0)
        total_sub_total = Decimal(0.0)
        total_initial_total = Decimal(0.0)
        total_total = Decimal(0.0)

        # Check if user has enough balance
        user_profile = get_object_or_404(Profile, user=user)
        for cart_item in cart_items:
            total_total += cart_item.total

        if user_profile.wallet_balance < total_total:
            raise PermissionDenied("Insufficient balance to complete the order.")

        with transaction.atomic():
            try:
                # Create CartOrder instance
                order = CartOrder.objects.create(
                    buyer=user,
                    payment_status="processing",
                    full_name=full_name,
                    email=email,
                    mobile=mobile,
                    address=address,
                    city=city,
                    state=state,
                    country=country,
                )

                # Create CartOrderItem instances
                for cart_item in cart_items:
                    CartOrderItem.objects.create(
                        order=order,
                        product=cart_item.product,
                        qty=cart_item.qty,
                        color=cart_item.color,
                        size=cart_item.size,
                        price=cart_item.price,
                        sub_total=cart_item.sub_total,
                        shipping_amount=cart_item.shipping_amount,
                        service_fee=cart_item.service_fee,
                        total=cart_item.total,
                        initial_total=cart_item.total,
                        vendor=cart_item.product.vendor
                    )

                    # Aggregate totals
                    total_shipping += cart_item.shipping_amount
                    total_service_fee += cart_item.service_fee
                    total_sub_total += cart_item.sub_total
                    total_initial_total += cart_item.total

                    # Add vendor to order
                    order.vendor.add(cart_item.product.vendor)

                # Update totals in CartOrder instance
                order.sub_total = total_sub_total
                order.shipping_amount = total_shipping
                order.service_fee = total_service_fee
                order.initial_total = total_initial_total
                order.total = total_total

                # Save CartOrder instance
                order.save()

                # Deduct the order total from user's wallet balance
                user_profile.wallet_balance -= total_total
                user_profile.save()

                # Delete cart items
                cart_items.delete()

            except Exception as e:
                raise APIException(f"An error occurred while creating the order: {str(e)}")

        # Return response indicating success
        return Response({"message": "Order Created Successfully", 'order_oid': order.oid}, status=status.HTTP_201_CREATED)





