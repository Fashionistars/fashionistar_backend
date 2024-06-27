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

stripe.api_key = settings.STRIPE_SECRET_KEY
PAYPAL_CLIENT_ID = settings.PAYPAL_CLIENT_ID
PAYPAL_SECRET_ID = settings.PAYPAL_SECRET_ID


def send_notification(user=None, vendor=None, order=None, order_item=None):
    Notification.objects.create(
        user=user,
        vendor=vendor,
        order=order,
        order_item=order_item,
    )

class ConfigSettingsDetailView(generics.RetrieveAPIView):
    serializer_class = ConfigSettingsSerializer

    def get_object(self):
        # Use the get method to retrieve the first ConfigSettings object
        return ConfigSettings.objects.first()

    permission_classes = (AllowAny,)

class FeaturedProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(status="published", featured=True)[:3]
    permission_classes = (AllowAny,)

class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(status="published")
    permission_classes = (AllowAny,)

class ProductDetailView(generics.RetrieveAPIView):
    """Display product details """
    serializer_class = ProductSerializer
    permission_classes = [AllowAny,]

    def get_object(self):
        # Retrieve the product using the provided slug from the URL
        slug = self.kwargs.get('slug')
        product = Product.objects.get(slug=slug)
        return product

    def get(self, request, *args, **kwargs):
        product = self.get_object()
        serializer = self.get_serializer(product)
        return Response(serializer.data, status=status.HTTP_200_OK)    
 



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


class CouponApiView(generics.CreateAPIView):
    serializer_class = CartOrderSerializer

    def create(self, request, *args, **kwargs):
        payload = request.data

        order_oid = payload['order_oid']
        coupon_code = payload['coupon_code']
        print("order_oid =======", order_oid)
        print("coupon_code =======", coupon_code)

        order = CartOrder.objects.get(oid=order_oid)
        coupon = Coupon.objects.filter(code__iexact=coupon_code, active=True).first()
        
        if coupon:
            order_items = CartOrderItem.objects.filter(order=order, vendor=coupon.vendor)
            if order_items:
                for i in order_items:
                    print("order_items =====", i.product.title)
                    if not coupon in i.coupon.all():
                        discount = i.total * coupon.discount / 100
                        
                        i.total -= discount
                        i.sub_total -= discount
                        i.coupon.add(coupon)
                        i.saved += discount
                        i.applied_coupon = True

                        order.total -= discount
                        order.sub_total -= discount
                        order.saved += discount

                        i.save()
                        order.save()
                        return Response( {"message": "Coupon Activated"}, status=status.HTTP_200_OK)
                    else:
                        return Response( {"message": "Coupon Already Activated"}, status=status.HTTP_200_OK)
            return Response( {"message": "Order Item Does Not Exists"}, status=status.HTTP_200_OK)
        else:
            return Response( {"message": "Coupon Does Not Exists"}, status=status.HTTP_404_NOT_FOUND)


    


class StripeCheckoutView(generics.CreateAPIView):
    serializer_class = CartOrderSerializer

    def create(self, request, *args, **kwargs):
        order_oid = self.kwargs['order_oid']
        order = CartOrder.objects.filter(oid=order_oid).first()

        if not order:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)


        try:
            checkout_session = stripe.checkout.Session.create(
                customer_email=order.email,
                payment_method_types=['card'],
                line_items=[
                    {
                        'price_data': {
                            'currency': 'usd',
                            'product_data': {
                                'name': order.full_name,
                            },
                            'unit_amount': int(order.total * 100),
                        },
                        'quantity': 1,
                    }
                ],
                mode='payment',
                # success_url = f"{settings.SITE_URL}/payment-success/{{order.oid}}/?session_id={{CHECKOUT_SESSION_ID}}",
                # cancel_url = f"{settings.SITE_URL}/payment-success/{{order.oid}}/?session_id={{CHECKOUT_SESSION_ID}}",

                success_url=settings.SITE_URL+'/payment-success/'+ order.oid +'?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=settings.SITE_URL+'/?session_id={CHECKOUT_SESSION_ID}',
            )
            order.stripe_session_id = checkout_session.id 
            order.save()

            return redirect(checkout_session.url)
        except stripe.error.StripeError as e:
            return Response( {'error': f'Something went wrong when creating stripe checkout session: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_access_token(client_id, secret_key):
    # Function to get access token from PayPal API
    token_url = 'https://api.sandbox.paypal.com/v1/oauth2/token'
    data = {'grant_type': 'client_credentials'}
    auth = (client_id, secret_key)
    response = requests.post(token_url, data=data, auth=auth)

    if response.status_code == 200:
        print("access_token ====", response.json()['access_token'])
        return response.json()['access_token']
    else:
        raise Exception(f'Failed to get access token from PayPal. Status code: {response.status_code}') 

    
class PaymentSuccessView(generics.CreateAPIView):
    serializer_class = CartOrderSerializer
    queryset = CartOrder.objects.all()
    
    
    def create(self, request, *args, **kwargs):
        payload = request.data
        
        order_oid = payload['order_oid']
        session_id = payload['session_id']
        payapl_order_id = payload['payapl_order_id']

        order = CartOrder.objects.get(oid=order_oid)
        order_items = CartOrderItem.objects.filter(order=order)

        if payapl_order_id != "null":
            paypal_api_url = f'https://api-m.sandbox.paypal.com/v2/checkout/orders/{payapl_order_id}'
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {get_access_token(PAYPAL_CLIENT_ID, PAYPAL_SECRET_ID)}',
            }
            response = requests.get(paypal_api_url, headers=headers)

            if response.status_code == 200:
                paypal_order_data = response.json()
                paypal_payment_status = paypal_order_data['status']
                if paypal_payment_status == 'COMPLETED':
                    if order.payment_status == "processing":
                        order.payment_status = "paid"
                        order.save()
                        if order.buyer != None:
                            send_notification(user=order.buyer, order=order)

                        merge_data = {
                            'order': order, 
                            'order_items': order_items, 
                        }
                        subject = f"Order Placed Successfully"
                        text_body = render_to_string("email/customer_order_confirmation.txt", merge_data)
                        html_body = render_to_string("email/customer_order_confirmation.html", merge_data)
                        
                        msg = EmailMultiAlternatives(
                            subject=subject, from_email=settings.FROM_EMAIL,
                            to=[order.email], body=text_body
                        )
                        msg.attach_alternative(html_body, "text/html")
                        msg.send()

                        for o in order_items:
                            send_notification(vendor=o.vendor, order=order, order_item=o)
                            
                            merge_data = {
                                'order': order, 
                                'order_items': order_items, 
                            }
                            subject = f"New Sale!"
                            text_body = render_to_string("email/vendor_order_sale.txt", merge_data)
                            html_body = render_to_string("email/vendor_order_sale.html", merge_data)
                            
                            msg = EmailMultiAlternatives(
                                subject=subject, from_email=settings.FROM_EMAIL,
                                to=[o.vendor.email], body=text_body
                            )
                            msg.attach_alternative(html_body, "text/html")
                            msg.send()

                        return Response( {"message": "Payment Successfull"}, status=status.HTTP_201_CREATED)
                    else:
                        
                        return Response( {"message": "Already Paid"}, status=status.HTTP_201_CREATED)
            

        # Process Stripe Payment
        if session_id != "null":
            session = stripe.checkout.Session.retrieve(session_id)

            if session.payment_status == "paid":
                if order.payment_status == "processing":
                    order.payment_status = "paid"
                    order.save()

                    if order.buyer != None:
                        send_notification(user=order.buyer, order=order)
                    for o in order_items:
                        send_notification(vendor=o.vendor, order=order, order_item=o)

                    return Response( {"message": "Payment Successfull"}, status=status.HTTP_201_CREATED)
                else:
                    return Response( {"message": "Already Paid"}, status=status.HTTP_201_CREATED)
                
            elif session.payment_status == "unpaid":
                return Response( {"message": "unpaid!"}, status=status.HTTP_402_PAYMENT_REQUIRED)
            elif session.payment_status == "canceled":
                return Response( {"message": "cancelled!"}, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response( {"message": "An Error Occured!"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            session = None


class ReviewRatingAPIView(generics.CreateAPIView):
    serializer_class = ReviewSerializer
    queryset = Review.objects.all()
    permission_classes = (AllowAny, )

    def create(self, request, *args, **kwargs):
        payload = request.data

        user_id = payload['user_id']
        product_id = payload['product_id']
        rating = payload['rating']
        review = payload['review']

        user = User.objects.get(id=user_id)
        product = Product.objects.get(id=product_id)

        Review.objects.create(user=user, product=product, rating=rating, review=review)
    
        return Response( {"message": "Review Created Successfully."}, status=status.HTTP_201_CREATED)



class ReviewListView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = (AllowAny, )

    def get_queryset(self):
        product_id = self.kwargs['product_id']

        product = Product.objects.get(id=product_id)
        reviews = Review.objects.filter(product=product)
        return reviews
    
class SearchProductsAPIView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        query = self.request.GET.get('query')
        print("query =======", query)

        products = Product.objects.filter(status="published", title__icontains=query)
        return products
       