# Django Packages
from rest_framework import generics, status
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, APIException
from django.core.exceptions import ObjectDoesNotExist

# Restframework Packages
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status

# Serializers
from notification.models import Notification
from notification.serializer import NotificationSerializer, NotificationSummarySerializer
from userauths.serializer import ProfileSerializer
from store.serializers import  CartOrderSerializer, WishlistSerializer
from customer.serializers import SetTransactionPasswordSerializer, ValidateTransactionPasswordSerializer
from customer.serializers import DeliveryContactSerializer, ShippingAddressSerializer

# Models
from userauths.models import Profile, User 
from store.models import  Product, CartOrder, Wishlist
from customer.models import DeliveryContact, ShippingAddress

# Others Packages





class SetTransactionPasswordView(generics.GenericAPIView):
    serializer_class = SetTransactionPasswordSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response({"message": "Transaction password set successfully."}, status=status.HTTP_200_OK)



class ValidateTransactionPasswordView(generics.GenericAPIView):
    serializer_class = ValidateTransactionPasswordSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = Profile.objects.get(user=request.user)
        if profile.check_transaction_password(serializer.validated_data['password']):
            return Response({"message": "Password validated successfully."}, status=status.HTTP_200_OK)
        return Response({"message": "Invalid transaction password."}, status=status.HTTP_400_BAD_REQUEST)



# DeliveryContact Views
class DeliveryContactListCreateView(generics.ListCreateAPIView):
    queryset = DeliveryContact.objects.all()
    serializer_class = DeliveryContactSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

class DeliveryContactDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = DeliveryContact.objects.all()
    serializer_class = DeliveryContactSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        pk = self.kwargs['pk']
        try:
            return get_object_or_404(DeliveryContact, pk=pk)
        except ObjectDoesNotExist as e:
            raise NotFound(f"Delivery contact not found: {str(e)}")
        except Exception as e:
            raise APIException(f"An error occurred: {str(e)}")



# ShippingAddress Views
class ShippingAddressListCreateView(generics.ListCreateAPIView):
    queryset = ShippingAddress.objects.all()
    serializer_class = ShippingAddressSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



class ShippingAddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ShippingAddress.objects.all()
    serializer_class = ShippingAddressSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        pk = self.kwargs['pk']
        try:
            return get_object_or_404(ShippingAddress, pk=pk)
        except ObjectDoesNotExist as e:
            raise NotFound(f"Shipping address not found: {str(e)}")
        except Exception as e:
            raise APIException(f"An error occurred: {str(e)}")
        



class OrdersAPIView(generics.ListAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        user = User.objects.get(id=user_id)

        orders = CartOrder.objects.filter(buyer=user, payment_status="paid")
        return orders
    



class OrdersDetailAPIView(generics.RetrieveAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = (AllowAny,)
    lookup_field = 'user_id'

    def get_object(self):
        user_id = self.kwargs['user_id']
        order_oid = self.kwargs['order_oid']
        user = User.objects.get(id=user_id)

        order = CartOrder.objects.get(buyer=user, payment_status="paid", oid=order_oid)
        return order
    

    
class WishlistCreateAPIView(generics.CreateAPIView):
    serializer_class = WishlistSerializer
    permission_classes = (AllowAny, )

    def create(self, request):
        payload = request.data 

        product_id = payload['product_id']
        user_id = payload['user_id']

        product = Product.objects.get(id=product_id)
        user = User.objects.get(id=user_id)

        wishlist = Wishlist.objects.filter(product=product,user=user)
        if wishlist:
            wishlist.delete()
            return Response( {"message": "Removed From Wishlist"}, status=status.HTTP_200_OK)
        else:
            wishlist = Wishlist.objects.create(
                product=product,
                user=user,
            )
            return Response( {"message": "Added To Wishlist"}, status=status.HTTP_201_CREATED)

    

class WishlistAPIView(generics.ListAPIView):
    serializer_class = WishlistSerializer
    permission_classes = (AllowAny, )

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        user = User.objects.get(id=user_id)
        wishlist = Wishlist.objects.filter(user=user,)
        return wishlist
    


class CustomerUpdateView(generics.RetrieveUpdateAPIView):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = (AllowAny, )






class OrderTrackingView(APIView):
    def get(self, request, order_id, *args, **kwargs):
        order = get_object_or_404(CartOrder, id=order_id)
        serializer = CartOrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)





class ClientNotificationUnSeenListAPIView(generics.ListAPIView):
    """
    Retrieve a list of unseen notifications for a specific user.

    Args:
        user_id (int): The ID of the user whose unseen notifications are to be retrieved.

    Returns:
        Response: A list of unseen notifications serialized in JSON format.

    Raises:
        404: If the user does not exist.
    """
    serializer_class = NotificationSerializer
    permission_classes = (AllowAny, )

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        user = User.objects.get(id=user_id)
        notifications = Notification.objects.filter(user=user, seen=False).order_by('date')
        return notifications

class ClientNotificationSeenListAPIView(generics.ListAPIView):
    """
    Retrieve a list of seen notifications for a specific user.

    Args:
        user_id (int): The ID of the user whose seen notifications are to be retrieved.

    Returns:
        Response: A list of seen notifications serialized in JSON format.

    Raises:
        404: If the user does not exist.
    """
    serializer_class = NotificationSerializer
    permission_classes = (AllowAny, )

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        user = User.objects.get(id=user_id)
        notifications = Notification.objects.filter(user=user, seen=True).order_by('date')
        return notifications

class ClientNotificationSummaryAPIView(generics.ListAPIView):
    """
    Retrieve a summary of notifications for a specific user, including counts of unseen, seen, and all notifications.

    Args:
        user_id (int): The ID of the user whose notification summary is to be retrieved.

    Returns:
        Response: A summary of notifications serialized in JSON format.

    Raises:
        404: If the user does not exist.
    """
    serializer_class = NotificationSummarySerializer

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        user = User.objects.get(id=user_id)
        
        un_read_noti = Notification.objects.filter(user=user, seen=False).count()
        read_noti = Notification.objects.filter(user=user, seen=True).count()
        all_noti = Notification.objects.filter(user=user).count()

        return [{
            'un_read_noti': un_read_noti,
            'read_noti': read_noti,
            'all_noti': all_noti,
        }]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class ClientNotificationMarkAsSeen(generics.RetrieveUpdateAPIView):
    """
    Mark a specific notification as seen for a specific user.

    Args:
        user_id (int): The ID of the user.
        noti_id (int): The ID of the notification to be marked as seen.

    Returns:
        Response: The updated notification serialized in JSON format.

    Raises:
        404: If the user or notification does not exist.
    """
    serializer_class = NotificationSerializer
    permission_classes = (AllowAny, )

    def get_object(self):
        user_id = self.kwargs['user_id']
        noti_id = self.kwargs['noti_id']
        user = User.objects.get(id=user_id)
        notification = Notification.objects.get(user=user, id=noti_id)
        notification.seen = True
        notification.save()
        return notification







