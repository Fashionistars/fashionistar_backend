from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
import logging

from store.models import Product, Wishlist
from store.serializers import WishlistSerializer
from userauths.models import User
from vendor.utils import fetch_user_and_vendor, client_is_owner

# Get logger for application
application_logger = logging.getLogger('application')






class WishlistCreateAPIView(generics.CreateAPIView):
    """
    API endpoint for clients to create a wishlist or remove product from wishlist.
     *   *URL:* /api/client/wishlist/create/
        *   *Method:* POST
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
         *   *Request Body (JSON):*
                json
                {
                 "product_id":  "b8b873bb-22b9-47f5-b0be-68668d077d60",  // The product to add or remove from the wishlist
                }
           *   *Response (JSON):*
                *   On success (HTTP 200 OK if it was a delete, and HTTP 201 Created for creating )
                        json
                         {
                            "message": "Removed From Wishlist" or "Added To Wishlist"
                         }
                       
                *   On failure (HTTP 404 or 500):
                     json
                     {
                         "error": "Error message" // Message if the profile could not be found or the user is not a client.
                     }
                    
                   Possible Error Messages:
                    * "You do not have permission to perform this action.": If the user is not a client
                   * "Product not found": If product with product_id is not found.
                   * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = WishlistSerializer
    permission_classes = (IsAuthenticated, )

    def create(self, request):
        """
        Handles the creation of a new Wishlist item
        """
        user = request.user
        try:
            user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)

            if error_response:
                application_logger.error(f"Error fetching user or vendor: {error_response}")
                return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)
            
            if user_obj.role != 'client':
                application_logger.error(f"User: {user.email} is not a client")
                return Response({
                'error': "You do not have permission to perform this action.",
                'Reason': f"User: {user.email} is not a client"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            payload = request.data 
            product_id = payload['product_id']

            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                application_logger.error(f"Product with id {product_id} not found.")
                raise NotFound("Product not found")

            wishlist = Wishlist.objects.filter(product=product,user=user_obj)
            if wishlist:
                wishlist.delete()
                application_logger.info(f"Removed product from wishlist for client {user.email}")
                return Response( {"message": "Removed From Wishlist"}, status=status.HTTP_200_OK)
            else:
                wishlist = Wishlist.objects.create(
                    product=product,
                    user=user_obj,
                )
                application_logger.info(f"Added product to wishlist for client {user.email}")
                return Response( {"message": "Added To Wishlist"}, status=status.HTTP_201_CREATED)
        except Exception as e:
             application_logger.error(f"An unexpected error occurred while creating or deleting wishlist for client, {e}")
             return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class WishlistAPIView(generics.ListAPIView):
    """
    API endpoint for retrieving a list of wishlist items for a specific client.
        *   *URL:* /api/client/wishlist/<user_id>/
        *   *Method:* GET
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
         *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        [
                           {
                             "id": "3a42df4c-b02b-4f62-ad50-7df09c3cb2d2",
                              product:{} //Product Objects and all data
                                 },
                                ...
                         ]
                       
                *   On failure (HTTP 400, 404 or 500):
                     json
                     {
                         "error": "Error message" // Message if the profile could not be found or the user is not a client.
                     }
                     
                  Possible Error Messages:
                   * "You do not have permission to perform this action.": If the user is not a client
                    *  "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = WishlistSerializer
    permission_classes = (IsAuthenticated, )

    
    def list(self, request, *args, **kwargs):
        """
        Retrieves a list of wishlist items for the authenticated client user.

        Lists the serialized data.
        """
       
        user = self.request.user

        try:
            user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
            if error_response:
                application_logger.error(f"Error fetching user or vendor: {error_response}")
                return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)


            if user_obj.role != 'client':
                application_logger.error(f"User with email: {user.email} is not a client. Profile not found")
                return Response(
                    {'error': f'You do not have permission to perform this action.',
                    'Reason' : f'{user.email} is not a client. Profile not found.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            

            try:
                wishlist = Wishlist.objects.filter(user=user_obj)
                serializer = self.get_serializer(wishlist, many=True)
                application_logger.info(f"Successfully retrieved Wish-List items for user {user.email}")
                return Response(serializer.data, status=status.HTTP_200_OK)
            except Exception as e:
                application_logger.error(f"An unexpected error occurred while listing wishlist items, {e}")
                return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

               
        except Exception as e:
             application_logger.error(f"An unexpected error occurred while retrieving wishlist, {e}")
             return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    