from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound
import logging

from store.models import Product, Review
from store.serializers import ReviewSerializer
from userauths.models import User
from vendor.utils import fetch_user_and_vendor, client_is_owner

# Get logger for application
application_logger = logging.getLogger('application')

class ReviewListView(generics.ListAPIView):
    """
    API endpoint for retrieving a list of approved reviews for a specific product.
    *   *URL:* /api/home/reviews/<str:product_id>/
    *   *Method:* GET
    *   *Authentication:* No authentication required, viewable by all.
       *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                         [
                             {
                               "id": "3a42df4c-b02b-4f62-ad50-7df09c3cb2d2",
                               "product":{
                                 "id": "65f833d3-51b7-40ae-a448-9393e952668c",
                                  "title": "Brand New Socks",
                                   ...
                                },
                                "profile": {
                                  "id": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                                   ...
                                 },
                               "rating": 5,
                               "review": "Good Product"
                              },
                                ...
                         ]
                       
                *   On failure (HTTP 404 or 500):
                     json
                     {
                         "error": "Error message" // Message if the profile could not be found or the user is not a client.
                     }
                     
                   Possible Error Messages:
                   *  "Product not found": If product with id is not found.
                   * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = ReviewSerializer
    permission_classes = (AllowAny, )

    def get_queryset(self):
        """
        Retrieves approved reviews for a specific product.
        """
        try:
            product_id = self.kwargs['product_id']
            product = Product.objects.get(id=product_id)
            reviews = Review.objects.filter(product=product, active=True).select_related('product', 'user__profile')
            return reviews
        except Product.DoesNotExist:
            application_logger.error(f"Product with id {product_id} not found.")
            raise NotFound("Product not found")
        except Exception as e:
            application_logger.exception("An unexpected error occurred while retrieving reviews.")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request, *args, **kwargs):
        """
        Lists the serialized data.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ReviewCreateAPIView(generics.CreateAPIView):
    """
    API endpoint for clients to create a new review for a product.
        *   *URL:* /api/client/reviews/create/
        *   *Method:* POST
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
         *   *Request Body (JSON):*
                json
                 {
                    "product_id":  "b8b873bb-22b9-47f5-b0be-68668d077d60",
                     "rating": 5,
                     "review": "A very great product",
                     
                }
           *   *Response (JSON):*
                *   On success (HTTP 201 Created):
                        json
                         {
                            "message": "Review Created Successfully."
                          }
                       
                *   On failure (HTTP 400, 404 or 500):
                     json
                     {
                         "error": "Error message" // Message if the profile could not be found or the user is not a client.
                     }
                     
                  Possible Error Messages:
                   * "You do not have permission to perform this action.": If the user is not a client
                    *  "Product not found": If product with id is not found.
                   * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = ReviewSerializer
    permission_classes = (IsAuthenticated, )

    def create(self, request, *args, **kwargs):
        """
        Handles the creation of a new Product instance, ensuring the request is made by a Client.
        """
        user = request.user
        try:
            user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
            if error_response:
                application_logger.error(f"Error fetching user or profile: {error_response}")
                return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)
            
            
            if user_obj.role != 'client':
                application_logger.error(f"User with email: {user.email} is not a client. Profile not found")
                return Response(
                    {'error': f'You do not have permission to perform this action.',
                    'Reason' : f'{user.email} is not a client. Profile not found.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            
            payload = request.data

            product_id = payload['product_id']
            rating = payload['rating']
            review = payload['review']

            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                application_logger.error(f"Product with id {product_id} does not exist.")
                raise NotFound("Product not found")
           
            review = Review.objects.create(user=user_obj, product=product, rating=rating, review=review)
            application_logger.info(f"Review Created Successfully. for User {user.email} and Product {product_id}")
            return Response( {"message": "Review Created Successfully."}, status=status.HTTP_201_CREATED)
        except Exception as e:
             application_logger.error(f"An unexpected error occurred while creating Review, {e}")
             return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)