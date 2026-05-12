# Homepage/product.py

from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
import logging
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from store.models import Product
from Homepage.serializers import ProductListDetailSerializer

# Get logger for application
application_logger = logging.getLogger('application')

class ProductListView(generics.ListAPIView):
    """
    API endpoint for retrieving a list of products, with filtering and pagination.
    *   *URL:* /api/home/products/
    *   *Method:* GET
    *   *Authentication:* No authentication required, viewable by all.
    *   *Query Parameters:* (Optional, for filtering and pagination)
    *   *Category (str): Filters all products that is inside any Category type
    *   *tags: (string): Filters all products that matches all tags.
    *   *search (string) : Searches all products that matches a certain keyword
        *   *page (int): Page number for pagination. Defaults to 1.
        *   *page_size (int): Number of products per page. Defaults to 10.
        *   *ordering (string): sort products by a certain field.
        *   *Response (JSON):*
              *   On success (HTTP 200 OK):
                       json
                       [
                            {
                            "id": "96609158-5597-465b-903e-85f35e4289d9",
                             "sku": "SKU238584",
                             "vendor": "ee82962d-6116-49eb-ac26-c76723e87d85",
                             "title": "Socks",
                             "image": null,
                              ...
                              },
                           ....
                        ]
                      
                *   On failure (HTTP 500):
                     json
                     {
                         "error": "Error message" // Message if the profile could not be found or the user is not a client.
                     }
                   
                   Possible Error Messages:
                    * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = ProductListDetailSerializer
    permission_classes = (AllowAny,)
    queryset = Product.objects.filter(status="published")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    #The filter of all results of the API
    filterset_fields = ['category__name', 'tags'] # Enables the filtering for the API with Category, Tags, Title and Status as well
    search_fields = ['title', 'description']  # Enable Search filter for the API ( description and the tilte)
    ordering_fields = ['title', 'price', 'date'] # Can order it by title, price or date if required

    def list(self, request, *args, **kwargs):
        """
        Lists the serialized data.
        """
        try:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            application_logger.info(f"Successfully retrieved and listed products for client")
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving and listing the product for a client, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)






class ProductDetailView(generics.RetrieveAPIView):
    """
    API endpoint for retrieving all details for a specific product, using the slug in the URL.
     *   *URL:* /api/home/product/<str:slug>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
           *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        [
                            {
                            "id": "96609158-5597-465b-903e-85f35e4289d9",
                             "sku": "SKU238584",
                             "vendor": "ee82962d-6116-49eb-ac26-c76723e87d85",
                             "title": "Socks",
                             "image": null,
                             "description": "Brand New Socks",
                              ...
                              },
                           ....
                        ]
                       
                *   On failure (HTTP 404 or 500):
                    json
                        {
                             "error": "Error message" // Message if the product is not found 
                             'REASON : 'Here The The Reason What Happen: To The Process' //Message more details about the Reason what happen
                         
                        }
                    
                   Possible Error Messages:
                    *  "Product not found": If product with slug does not exist.
                   * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = ProductListDetailSerializer
    permission_classes = (AllowAny,)
    queryset = Product.objects.all()
    lookup_field = 'slug'

    def retrieve(self, request, *args, **kwargs):
        """
        Retrieves the serialized data for a specific product using the slug.
        """
        try:
            slug = self.kwargs['slug']
            product = Product.objects.get(slug=slug, status="published")  # Only published products
            serializer = self.get_serializer(product)
            application_logger.info(f"Successfully retrieved product with slug: {slug}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Product.DoesNotExist:
            application_logger.error(f"Product with slug {slug} not found.")
            return Response({'error': 'Product not found', 'REASON' : f'Product with slug = {slug} is not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving product with slug {self.kwargs['slug']}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)