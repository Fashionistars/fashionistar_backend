from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated

from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone


from decimal import Decimal
from datetime import timedelta

# Models 
from store.models import CartOrder, CartOrderItem
from userauths.models import User 
from vendor.models import Vendor
from notification.models import Notification, CancelledOrder

# Serializers
from notification.serializer import NotificationSerializer, NotificationSummarySerializer

# Ensure to add logger setup at the beginning of your module
import logging
logger = logging.getLogger(__name__)





class CancelOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Cancel an order.
        Steps:
        1. Fetch the order using the provided order_oid.
        2. Check if the request is from the user or vendor.
        3. Perform cancellation logic based on the request origin.
        4. Send cancellation notifications and emails.
        Payload: {'order_oid': str, 'reason': str}
        """
        order_oid = request.data.get('order_oid')
        reason = request.data.get('reason', '')

        try:
            # Fetch the order and order items
            order = CartOrder.objects.get(oid=order_oid)
            order_items = CartOrderItem.objects.filter(order=order)

            # Check if the request is from the user or vendor
            if request.user == order.buyer:
                # User cancellation logic
                if timezone.now() - order.date > timedelta(hours=24):
                    raise PermissionDenied("Order cannot be cancelled after 24 hours.")
                self.cancel_order(order, order_items, reason, is_user=True)
                return Response({"message": "Order successfully cancelled by user"}, status=status.HTTP_200_OK)
            elif request.user in order.vendor.all():
                # Vendor cancellation logic
                self.cancel_order(order, order_items, reason, is_user=False)
                return Response({"message": "Order successfully cancelled by vendor"}, status=status.HTTP_200_OK)
            else:
                raise PermissionDenied("You do not have permission to cancel this order.")

        except CartOrder.DoesNotExist:
            return Response({"message": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in CancelOrderView: {e}")
            return Response({"message": "An error occurred while cancelling the order"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def cancel_order(self, order, order_items, reason, is_user):
        """
        Helper function to cancel an order.
        Steps:
        1. Set order status to 'Cancelled'.
        2. Create CancelledOrder instances.
        3. Refund the buyer if necessary.
        4. Notify the vendor and refund their balance.
        5. Send cancellation emails.
        """
        # Set order status to 'Cancelled'
        order.order_status = "Cancelled"
        order.save()

        # Create CancelledOrder instances and handle refunds
        for item in order_items:
            CancelledOrder.objects.create(
                user=order.buyer,
                order_item=item,
                email=order.buyer.email
            )

            if not is_user:
                order.buyer.profile.wallet_balance += item.total
                order.buyer.profile.save()

            Notification.objects.create(
                vendor=item.vendor,
                order=order,
                order_item=item,
                notification_type="order_cancelled"
            )

            item.vendor.balance -= item.total * Decimal(0.9)
            item.vendor.save()

        # Send cancellation emails
        self.send_cancellation_email(order.buyer.email, reason)
        for item in order_items:
            self.send_cancellation_email(item.vendor.email, reason)

    def send_cancellation_email(self, email, reason):
        """
        Helper function to send cancellation emails.
        Payload: email, reason
        """
        subject = "Order Cancellation Notice"
        message = f"Your order has been cancelled. Reason: {reason}"
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])




# Client Notification Endpoints
class ClientNotificationUnSeenListAPIView(generics.ListAPIView):
    """
    Retrieve a list of unseen notifications for a specific user.
    Steps:
    1. Retrieve the user by ID.
    2. Filter notifications by user and unseen status.
    3. Serialize and return the notifications.
    Payload: None
    """
    serializer_class = NotificationSerializer
    permission_classes = (AllowAny, )

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        try:
            user = User.objects.get(id=user_id)
            notifications = Notification.objects.filter(user=user, seen=False).order_by('date')
            return notifications
        except User.DoesNotExist:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in ClientNotificationUnSeenListAPIView: {e}")
            return Response({"message": "An error occurred while retrieving notifications"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ClientNotificationSeenListAPIView(generics.ListAPIView):
    """
    Retrieve a list of seen notifications for a specific user.
    Steps:
    1. Retrieve the user by ID.
    2. Filter notifications by user and seen status.
    3. Serialize and return the notifications.
    Payload: None
    """
    serializer_class = NotificationSerializer
    permission_classes = (AllowAny, )

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        try:
            user = User.objects.get(id=user_id)
            notifications = Notification.objects.filter(user=user, seen=True).order_by('date')
            return notifications
        except User.DoesNotExist:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in ClientNotificationSeenListAPIView: {e}")
            return Response({"message": "An error occurred while retrieving notifications"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClientNotificationSummaryAPIView(generics.ListAPIView):
    """
    Retrieve a summary of notifications for a specific user, including counts of unseen, seen, and all notifications.
    Steps:
    1. Retrieve the user by ID.
    2. Count unseen, seen, and total notifications.
    3. Return the summary data.
    Payload: None
    """
    serializer_class = NotificationSummarySerializer

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        try:
            user = User.objects.get(id=user_id)
            un_read_noti = Notification.objects.filter(user=user, seen=False).count()
            read_noti = Notification.objects.filter(user=user, seen=True).count()
            all_noti = Notification.objects.filter(user=user).count()
            return [{
                'un_read_noti': un_read_noti,
                'read_noti': read_noti,
                'all_noti': all_noti,
            }]
        except User.DoesNotExist:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in ClientNotificationSummaryAPIView: {e}")
            return Response({"message": "An error occurred while retrieving notification summary"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request, *args, **kwargs):
        """
        List the notification summary.
        Steps:
        1. Get the queryset.
        2. Serialize the data.
        3. Return the serialized data.
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)



class ClientNotificationMarkAsSeen(generics.RetrieveUpdateAPIView):
    """
    Mark a specific notification as seen for a specific user.
    Steps:
    1. Retrieve the user and notification by their IDs.
    2. Update the seen status of the notification to True.
    3. Save the changes.
    Payload: None
    """
    serializer_class = NotificationSerializer
    permission_classes = (AllowAny, )

    def get_object(self):
        user_id = self.kwargs['user_id']
        noti_id = self.kwargs['noti_id']
        try:
            user = User.objects.get(id=user_id)
            notification = Notification.objects.get(user=user, id=noti_id)
            notification.seen = True
            notification.save()
            return notification
        except User.DoesNotExist:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        except Notification.DoesNotExist:
            return Response({"message": "Notification not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in ClientNotificationMarkAsSeen: {e}")
            return Response({"message": "An error occurred while marking the notification as seen"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
