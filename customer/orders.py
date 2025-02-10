from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
import logging

from store.models import Product, CartOrder, CartOrderItem, Coupon
from store.serializers import CartOrderSerializer, CartOrderItemSerializer
from userauths.models import User
from vendor.utils import fetch_user_and_vendor, client_is_owner

# Get logger for application
application_logger = logging.getLogger('application')

class OrdersAPIView(generics.ListAPIView):
    """
    API endpoint for retrieving a list of paid orders for the authenticated client.
        *   *URL:* /api/client/orders/<int:user_id>/
        *   *Method:* GET
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
        *   *Request Body:* None
          *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        [
                            {
                            "id": "d14b26e4-4250-4824-9643-5262b0109521",
                            "vendor": [
                                 "ee82962d-6116-49eb-ac26-c76723e87d85"
                            ],
                            "buyer": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                             "sub_total": 3000.00,
                             "shipping_amount": 1000.00,
                              "service_fee": 50.00,
                            "total": 4050.00,
                             ...
                            },
                                 ....
                         ]
                       
                *   On failure (HTTP 400, 404 or 500):
                    json
                        {
                             "error": "Error message" // Message if the profile could not be found or the user is not a client.
                         }
                   
                   Possible Error Messages:
                   * "You do not have permission to perform this action.": If the user is not a client
                   * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = CartOrderSerializer
    permission_classes = (IsAuthenticated,)  # Ensure the user is authenticated
    

    def list(self, request, *args, **kwargs):
        """
        Retrieves the list of all the orders of a certain client that are paid.
        """
        user = self.request.user
        try:
            user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
            if error_response:
                application_logger.error(f"Error fetching user or profile: {error_response}")
                return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)
            
            
            # if user_obj.role != 'client':
            #     application_logger.error(f"User with id {user.pk} is not a client. Cant retrieve cart objects for {user.email}")
            #     return Response(
            #         {'error': f'You do not have permission to perform this action.',
            #         'Reason' : f"User with id {user.pk} is not a client. Cant retrieve cart objects for {user.email}"
            #         }, status=status.HTTP_400_BAD_REQUEST)
            

            try:
                orders = CartOrder.objects.filter(buyer=user_obj, payment_status="paid")
                serializer = self.get_serializer(orders, many=True)
                application_logger.info(f"Successfully retrieved orders for client {user.email}")
                return Response(serializer.data, status=status.HTTP_200_OK)
            except Exception as e:
                application_logger.error(f"An unexpected error occurred while retrieving orders for client {user.email}: {e}")
                return Response({'error': f'An error occurred while fetching orders: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except PermissionDenied as e:
            application_logger.error(f"Permission denied: {e} for user {user.email}")
            return Response({'error': f'You do not have permission to perform this action.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving orders for a client, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

























from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
import logging

from store.models import Product, CartOrder, CartOrderItem, Coupon
from store.serializers import CartOrderSerializer, CartOrderItemSerializer
from userauths.models import User
from vendor.utils import fetch_user_and_vendor, client_is_owner

# Get logger for application
application_logger = logging.getLogger('application')


class OrdersAPIView(generics.ListAPIView):
    """
    API endpoint for retrieving a list of paid orders for the authenticated client.
        *   *URL:* /api/client/orders/<int:user_id>/
        *   *Method:* GET
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
        *   *Request Body:* None
          *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        [
                            {
                            "id": "d14b26e4-4250-4824-9643-5262b0109521",
                            "vendor": [
                                 "ee82962d-6116-49eb-ac26-c76723e87d85"
                            ],
                            "buyer": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                             "sub_total": 3000.00,
                             "shipping_amount": 1000.00,
                              "service_fee": 50.00,
                            "total": 4050.00,
                             ...
                            },
                                 ....
                         ]
                       
                *   On failure (HTTP 400, 404 or 500):
                    json
                        {
                             "error": "Error message" // Message if the profile could not be found or the user is not a client.
                         }
                   
                   Possible Error Messages:
                   * "You do not have permission to perform this action.": If the user is not a client
                   * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = CartOrderSerializer
    permission_classes = (IsAuthenticated,)  # Ensure the user is authenticated


    def list(self, request, *args, **kwargs):
        """
        Retrieves the list of all the orders of a certain client that are paid.
        """
        user = self.request.user
        try:
            user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
            if error_response:
                application_logger.error(f"Error fetching user or profile: {error_response}")
                return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)
            
            if user_obj.role == 'client':
                try:
                    orders = CartOrder.objects.filter(buyer=user_obj, payment_status="paid")
                    serializer = self.get_serializer(orders, many=True)
                    application_logger.info(f"Successfully retrieved orders for client {user.email}")
                    return Response(serializer.data, status=status.HTTP_200_OK)
                except Exception as e:
                  application_logger.error(f"An unexpected error occurred while retrieving orders for client {user.email}: {e}")
                  return Response({'error': f'An error occurred while fetching orders: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                application_logger.error(f"User with id {user.pk} is not a client. Cant retrieve cart objects for {user.email}")
                raise PermissionDenied("You do not have permission to perform this action.")
        except PermissionDenied as e:
            application_logger.error(f"Permission denied: {e} for user {user.email}")
            return Response({'error': f'You do not have permission to perform this action.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving orders for a client, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OrdersDetailAPIView(generics.RetrieveAPIView):
    """
    API endpoint for retrieving a specific paid order by its oid for the authenticated client.
      *   *URL:* /api/client/order/detail/<str:user_id>/<str:order_oid>/
        *   *Method:* GET
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
        *   *Request Body:* None
            *   *Response (JSON):*
                    *   On success (HTTP 200 OK):
                            json
                            {
                            "id": "d14b26e4-4250-4824-9643-5262b0109521",
                            "vendor": [
                                    "ee82962d-6116-49eb-ac26-c76723e87d85"
                                ],
                            "buyer": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                            "sub_total": 3000.00,
                            "shipping_amount": 1000.00,
                            "service_fee": 50.00,
                            "total": 4050.00,
                            "payment_status": "initiated",
                            ...
                           }
                        
                    *   On failure (HTTP 400, 404 or 500):
                        json
                            {
                                 "error": "Error message" // Message if the profile could not be found or the user is not a client.
                             }
                      
                      Possible Error Messages:
                        *   "You do not have permission to perform this action.": If the user is not a client
                        *   "Order not found": If the order with the provided oid is not found.
                        *   "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.

    """
    serializer_class = CartOrderSerializer
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        """
        Retrieves the serialized order data.
        """
        user = self.request.user
        try:
            user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
            if error_response:
                application_logger.error(f"Error fetching user or vendor: {error_response}")
                return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)

            if user_obj.role != 'client':
                application_logger.error(f"User: {user.email} is not a client")
                return Response({'error': "You do not have permission to perform this action."}, status=status.HTTP_400_BAD_REQUEST)
            
            user_id = self.kwargs['user_id']
            order_oid = self.kwargs['order_oid']

            try:
                 order = CartOrder.objects.get(buyer=user_obj, payment_status="paid", oid=order_oid)
            except CartOrder.DoesNotExist:
                 application_logger.error(f"Order with oid {order_oid} not found for user {user.email}")
                 return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

            serializer = self.get_serializer(order)
            application_logger.info(f"Successfully retrieved details for order {order_oid} for user {user.email}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except PermissionDenied as e:
            application_logger.error(f"Permission denied: {e} for user {user.email}")
            return Response({'error': f'You do not have permission to perform this action.'}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving order details for user {user.email}, oid {self.kwargs['order_oid']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)            