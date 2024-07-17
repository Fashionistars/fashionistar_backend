

from backend import settings

from notification.utils import send_notification


from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated

from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.utils import timezone


from decimal import Decimal
from datetime import timedelta

# Models 
from store.models import CartOrder, CartOrderItem
from userauths.models import User 
from vendor.models import Vendor
from notification.models import Notification, CancelledOrder

# Serializers
from notification.serializer import NotificationSerializer

# Ensure to add logger setup at the beginning of your module
import logging
logger = logging.getLogger(__name__)







logger = logging.getLogger(__name__)



# Views with robust error handling and comments


class VendorRejectOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Vendor rejects an order item.
        Steps:
        1. Fetch the order item using the provided order_item_oid.
        2. Check if the request is from the vendor.
        3. Perform rejection logic.
        4. Send rejection notifications and emails.
        Payload: {'order_item_oid': str, 'reason': str}
        """
        order_item_oid = request.data.get('order_item_oid')
        reason = request.data.get('reason', '')

        try:
            # Fetch the order item
            order_item = CartOrderItem.objects.get(oid=order_item_oid)

            # Check if the request is from the vendor
            if request.user == order_item.vendor.user:
                # Vendor rejection logic
                self.reject_order_item(order_item, reason)
                return Response({"message": "Order item successfully rejected by vendor"}, status=status.HTTP_200_OK)
            else:
                raise PermissionDenied("You do not have permission to reject this order item.")

        except CartOrderItem.DoesNotExist:
            return Response({"message": "Order item not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in VendorRejectOrderView: {e}")
            return Response({"message": "An error occurred while rejecting the order item"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def reject_order_item(self, order_item, reason):
        """
        Helper function to reject an order item.
        Steps:
        1. Set order item status to 'Rejected'.
        2. Create CancelledOrder instance.
        3. Refund the buyer.
        4. Notify the vendor and refund their balance.
        5. Send rejection emails.
        """
        # Set order item status to 'Rejected'
        order_item.order_status = "Rejected"
        order_item.save()

        # Create CancelledOrder instance and handle refunds
        CancelledOrder.objects.create(
            user=order_item.order.buyer,
            order_item=order_item,
            email=order_item.order.buyer.email
        )

        order_item.order.buyer.profile.wallet_balance += order_item.total
        order_item.order.buyer.profile.save()

        Notification.objects.create(
            vendor=order_item.vendor,
            order=order_item.order,
            order_item=order_item,
            notification_type="offer_rejected"
        )

        order_item.vendor.balance -= order_item.total * Decimal(0.9)
        order_item.vendor.save()

        # Send rejection emails
        self.send_rejection_email(order_item.order.buyer.email, reason)
        self.send_rejection_email(order_item.vendor.email, reason)

    def send_rejection_email(self, email, reason):
        """
        Helper function to send rejection emails.
        Payload: email, reason
        """
        subject = "Order Item Rejection Notice"
        message = f"Your order item has been rejected. Reason: {reason}"
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])



class VendorUpdateOrderStatusView(APIView):
    permission_classes = (IsAuthenticated, )
    
    def post(self, request, order_item_id, *args, **kwargs):
        """
        Vendor updates the order item status.
        Steps:
        1. Retrieve the order item.
        2. Verify the vendor.
        3. Check if the action is 'accept' or 'reject'.
        4. If 'accept' and production status is 'Pending', change status to 'Accepted' and save.
        5. If 'reject' and production status is 'Pending', change status to 'Rejected' and save.
        6. Create a notification for the updated order status.
        Payload: {"action": "accept" or "reject"}
        """
        try:
            user = self.request.user
            user_role = User.objects.values_list('role', flat=True).get(pk=user.pk)
        except User.DoesNotExist:
            raise PermissionDenied("Permission Denied!")

        if user_role != 'Vendor':
            raise PermissionDenied("You do not have permission to perform this action.")
        
        order_item = get_object_or_404(CartOrderItem, id=order_item_id)
        
        if order_item.vendor.user != user:
            raise PermissionDenied("You do not have permission to update this order.")

        action = request.data.get("action")
        if action not in ["accept", "reject"]:
            return Response({"message": "Invalid action. Please specify 'accept' or 'reject'."},
                            status=status.HTTP_400_BAD_REQUEST)
        
        if order_item.production_status == 'Pending':
            if action == "accept":
                order_item.production_status = 'Accepted'
            elif action == "reject":
                order_item.production_status = 'Rejected'
            order_item.save()
            send_notification(
                user=order_item.order.user,
                vendor=order_item.vendor,
                order=order_item.order,
                order_item=order_item,
                notification_type=f"order_{action}ed"
            )
            return Response({"message": f"Order {action}ed"}, status=status.HTTP_200_OK)
        
        return Response({"message": "Order status cannot be updated from its current state."}, status=status.HTTP_400_BAD_REQUEST)


class VendorCompleteOrderView(APIView):
    def post(self, request, order_item_id, *args, **kwargs):
        """
        Vendor marks an order item as completed.
        Steps:
        1. Retrieve the order item.
        2. Check if the production status is 'Accepted'.
        3. If yes, change status to 'Completed' and save.
        4. Create a notification for the completed order.
        Payload: None
        """
        try:
            order_item = get_object_or_404(CartOrderItem, id=order_item_id)
            if order_item.production_status == 'Accepted':
                order_item.production_status = 'Completed'
                order_item.save()
                send_notification(
                    user=order_item.user,
                    vendor=order_item.vendor,
                    order=order_item.order,
                    order_item=order_item,
                    notification_type="order_completed"
                )
                return Response({"message": "Order completed"}, status=status.HTTP_200_OK)
            return Response({"message": "Order not accepted or already completed"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VendorOrderNotificationView(APIView):
    def get(self, request, vendor_id, *args, **kwargs):
        """
        Retrieve notifications for a specific vendor.
        Steps:
        1. Filter notifications based on vendor_id.
        2. Serialize the notifications.
        3. Return the serialized data.
        Payload: None
        """
        try:
            notifications = Notification.objects.filter(vendor_id=vendor_id)
            serializer = NotificationSerializer(notifications, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationUnSeenListAPIView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = (AllowAny, )

    def get_queryset(self):
        """
        Retrieve unseen notifications for a specific vendor.
        Steps:
        1. Get the vendor ID from the URL.
        2. Filter notifications by vendor and unseen status.
        3. Order the notifications.
        Payload: None
        """
        try:
            vendor_id = self.kwargs['vendor_id']
            vendor = Vendor.objects.get(id=vendor_id)
            return Notification.objects.filter(vendor=vendor, seen=False).order_by('date')
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationSeenListAPIView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = (AllowAny, )

    def get_queryset(self):
        """
        Retrieve seen notifications for a specific vendor.
        Steps:
        1. Get the vendor ID from the URL.
        2. Filter notifications by vendor and seen status.
        3. Order the notifications.
        Payload: None
        """
        try:
            vendor_id = self.kwargs['vendor_id']
            vendor = Vendor.objects.get(id=vendor_id)
            return Notification.objects.filter(vendor=vendor, seen=True).order_by('date')
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationSummaryAPIView(APIView):
    def get(self, request, vendor_id, *args, **kwargs):
        """
        Retrieve a summary of notifications for a specific vendor.
        Steps:
        1. Get the vendor ID from the URL.
        2. Count unseen, seen, and total notifications.
        3. Return the summary data.
        Payload: None
        """
        try:
            vendor = get_object_or_404(Vendor, id=vendor_id)
            unseen_count = Notification.objects.filter(vendor=vendor, seen=False).count()
            seen_count = Notification.objects.filter(vendor=vendor, seen=True).count()
            total_count = unseen_count + seen_count
            summary = {
                "unseen": unseen_count,
                "seen": seen_count,
                "total": total_count
            }
            return Response(summary, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationMarkAsSeen(APIView):
    def post(self, request, vendor_id, noti_id, *args, **kwargs):
        """
        Mark a specific notification as seen for a specific vendor.
        Steps:
        1. Retrieve the vendor and notification by their IDs.
        2. Update the seen status of the notification to True.
        3. Save the changes.
        Payload: None
        """
        try:
            vendor = get_object_or_404(Vendor, id=vendor_id)
            notification = get_object_or_404(Notification, id=noti_id, vendor=vendor)
            notification.seen = True
            notification.save()
            return Response({"message": "Notification marked as seen"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
