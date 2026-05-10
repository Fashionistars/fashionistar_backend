
# Django Packages
from django.db import models
from django.db import transaction
from django.contrib.auth import get_user_model
from django.db.models.functions import ExtractMonth
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Sum, F

# Restframework Packages
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import PermissionDenied

# Serializers
from userauths.serializer import  ProfileSerializer
from store.serializers import  CouponSummarySerializer, EarningSummarySerializer,SummarySerializer, CartOrderItemSerializer, ProductSerializer, CartOrderSerializer, GallerySerializer, ReviewSerializer,  SpecificationSerializer, CouponSerializer, ColorSerializer, SizeSerializer, VendorSerializer
from vendor.serializers import *

# Models
from userauths.models import Profile, User
from store.models import CartOrderItem,  Product,  CartOrder,  Review, Coupon
from vendor.models import Vendor

# Others Packages
from datetime import datetime, timedelta


import logging
from vendor.utils import fetch_user_and_vendor, vendor_is_owner  # Import the utility functions



application_logger = logging.getLogger('application')




from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
import logging
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from store.models import Product
from store.serializers import ProductSerializer

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
    serializer_class = ProductSerializer
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
    serializer_class = ProductSerializer
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
                            




class ProductsAPIView(generics.ListAPIView):
    """
        API endpoint for retrieving all products from a specific vendor.
        *   *URL:* /api/vendor/products/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
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
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                    
                Possible Error Messages:
                * "Vendor not found": If the vendor profile was not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.

    """
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """
        Retrieves and returns the product details for a specific vendor using the vendor_id.
        """
        try:
            vendor_id = self.kwargs['vendor_id']
            vendor = Vendor.objects.get(id=vendor_id)
            products = Product.objects.filter(vendor=vendor)
            return products
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor with id {vendor_id} does not exist.")
            raise NotFound("Vendor not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving product for vendor with id {vendor_id}, {e}")
        return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def list(self, request, *args, **kwargs):
        """
        Lists the serialized data.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while listing products for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class OrdersAPIView(generics.ListAPIView):
    """
    API view to retrieve a list of paid orders for the authenticated vendor.
        *   *URL:* /api/vendor/orders/
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
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                
                Possible Error Messages:
                * "You do not have permission to perform this action.": If the user is not a vendor
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = CartOrderSerializer
    permission_classes = (IsAuthenticated,)  # Ensure the user is authenticated

    def get_queryset(self):
        """
        Override the default get_queryset method to filter orders by the authenticated vendor.
        Retrieves the vendor associated with the authenticated user and returns their orders.
        
        Check if the user has permission to access the dashboard stats.
        """
        user = self.request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)
        
            orders = CartOrder.objects.filter(vendor=vendor_obj).prefetch_related('orderitem')
            return orders
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving orders for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def list(self, request, *args, **kwargs):
        """
        Lists the serialized data.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while listing orders for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OrderDetailAPIView(generics.RetrieveAPIView):
    """
    API endpoint for retrieving a specific paid order by its oid for the authenticated vendor.
    *   *URL:* /api/vendor/orders/<str:order_oid>/
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
                                "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                            }
                    
                    Possible Error Messages:
                        *   "You do not have permission to perform this action.": If the user is not a vendor
                        *   "Order not found": If the order with the provided oid is not found.
                        *   "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.

    """
    serializer_class = CartOrderSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        """
        Override the default get_object method to retrieve a specific order for the authenticated vendor.
        """
        user = self.request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)
            
            order_oid = self.kwargs['order_oid']
            try:
                order = CartOrder.objects.get(vendor=vendor_obj, oid=order_oid).prefetch_related('orderitem')
            except CartOrder.DoesNotExist:
                application_logger.error(f"Order with oid {order_oid} not found for vendor {user.email}")
                raise NotFound("Order not found")
            return order
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving order with oid {self.kwargs['order_oid']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def retrieve(self, request, *args, **kwargs):
        """
        Returns the serialized order data.
        """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving order details {self.kwargs['order_oid']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RevenueAPIView(generics.ListAPIView):
    """
        API endpoint for retrieving the total revenue for a specific vendor.
        *   *URL:* /api/vendor/revenue/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        [
                        200000
                        ]
                    
                *   On failure (HTTP 404 or 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                    
                Possible Error Messages:
                * "Vendor not found": If the vendor profile was not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = CartOrderItemSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """
        Retrieves and returns the total revenue for a specific vendor using the vendor_id.
        """
        try:
            vendor_id = self.kwargs['vendor_id']
            vendor = Vendor.objects.get(id=vendor_id)
            revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid").aggregate(
                total_revenue=Sum(F('sub_total') + F('shipping_amount')))['total_revenue'] or 0
            return [revenue]
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor with id {vendor_id} not found.")
            raise NotFound("Vendor not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving revenue for vendor with id {vendor_id}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def list(self, request, *args, **kwargs):
        """
        Lists the serialized data.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while listing revenues for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class YearlyOrderReportChartAPIView(generics.ListAPIView):
    """
    API endpoint for retrieving yearly order report chart for a specific vendor.
        *   *URL:* /api/vendor/yearly-report/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                    [
                            {
                            "order__date": "2024-01-29T15:39:14.964109+00:00",
                            "product": "42302a18-79f8-49d5-a8f6-9f3a6e256a7e",
                            "id__count": 1
                            },
                                ...
                        ]
                    
                *   On failure (HTTP 404 or 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                
                Possible Error Messages:
                * "Vendor not found": If the vendor profile was not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = CartOrderItemSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """
        Retrieves the yearly order report data for a specific vendor.
        """
        try:
            vendor_id = self.kwargs['vendor_id']
            vendor = Vendor.objects.get(id=vendor_id)

            # Include the 'product' field in the queryset
            report = CartOrderItem.objects.filter(
                vendor=vendor,
                order__payment_status="paid"
            ).select_related('product').values(
                'order__date', 'product'
            ).annotate(models.Count('id'))

            return report
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor with id {vendor_id} not found.")
            raise NotFound("Vendor not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving yearly order report for vendor with id {vendor_id}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request, *args, **kwargs):

        """
        Lists the serialized data.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while listing yearly order report for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
            

@api_view(('GET',))
def MonthlyOrderChartAPIFBV(request, vendor_id):
    """
        API endpoint for retrieving monthly order chart for a specific vendor.
        *   *URL:* /api/vendor/orders-report-chart/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        [
                        {
                            "month": 1,
                            "orders": 3
                        },
                            ...
                        ]
                    
                *   On failure (HTTP 404 or 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                    
                Possible Error Messages:
                * "Vendor not found": If the vendor profile was not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    try:
        vendor = Vendor.objects.get(id=vendor_id)
        orders = CartOrder.objects.filter(vendor=vendor)
        orders_by_month = orders.annotate(month=ExtractMonth("date")).values(
            "month").annotate(orders=models.Count("id")).order_by("month")
        return Response(orders_by_month)
    except Vendor.DoesNotExist:
        application_logger.error(f"Vendor with id {vendor_id} not found.")
        return Response({'error': 'Vendor not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        application_logger.error(f"An unexpected error occurred while retrieving monthly order chart for vendor with id {vendor_id}, {e}")
        return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

@api_view(('GET',))
def MonthlyProductsChartAPIFBV(request, vendor_id):
    """
    API endpoint for retrieving monthly product chart for a specific vendor.
        *   *URL:* /api/vendor/products-report-chart/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        [
                        {
                            "month": 1,
                            "orders": 4
                            },
                                ...
                        ]
                    
                *   On failure (HTTP 404 or 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                    
                Possible Error Messages:
                * "Vendor not found": If the vendor profile was not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    try:
        vendor = Vendor.objects.get(id=vendor_id)
        products = Product.objects.filter(vendor=vendor)
        products_by_month = products.annotate(month=ExtractMonth("date")).values(
        "month").annotate(orders=models.Count("id")).order_by("month")
        return Response(products_by_month)
    except Vendor.DoesNotExist:
        application_logger.error(f"Vendor with id {vendor_id} not found.")
        return Response({'error': 'Vendor not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving monthly product chart for vendor with id {vendor_id}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
















class ProductCreateView(generics.CreateAPIView):
    """
    API endpoint for vendors to create a new product.
    *   *URL:* /api/vendor/product-create/
        *   *Method:* POST
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
        *   *Request Body (JSON):*
                json
                {
                "title": "Brand New Item",  // Vendor's product title
                "description": "This is a brand new item",  // Vendor's product description
                "category": [],  // Vendor's product category
                    "tags": "fashion, clothing",   // Vendor's product tags
                    "brand": "Gucci",   // Vendor's product brand
                    "price": 3000.00,   // Vendor's product price
                    "shipping_amount": 1000.00,   // Vendor's product shipping_amount
                    "stock_qty": 100,  // Vendor's product stock_qty
                    "image": "/media/uploads/product.png"   // Vendor's product image
                    "specifications[0][title]": "Made In",   // Vendor's product specification 1 title
                    "specifications[0][content]": "Nigeria",   // Vendor's product specification 1 content
                    "colors[0][name]": "Green",  // Vendor's product color 1 name
                    "colors[0][color_code]": "#00FF00",  // Vendor's product color 1 color_code
                    "sizes[0][name]": "M",  // Vendor's product size 1 name
                "sizes[0][price]": 1000.00,  // Vendor's product size 1 price
                "gallery[0][image]": "/media/uploads/gallery_image_1.png" // Vendor's product gallery 1 image
                }
        *   *Response (JSON):*
                *   On success (HTTP 201 Created):
                        json
                        {
                        "id": "96609158-5597-465b-903e-85f35e4289d9",
                            "sku": "SKU238584",
                            "vendor": "ee82962d-6116-49eb-ac26-c76723e87d85",
                            "title": "Socks",
                            "image": null,
                            "description": "Brand New Socks",
                            ...
                        }
                    
                *   On failure (HTTP 400, 404 or 500):
                    json
                    {
                        "error": "Error message" // Error message explaining the failure
                    }
                    
                Possible error messages:
                * "You do not have permission to perform this action.": if the user is not a vendor
                * "Only vendors can create products.": if the user is not a vendor.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [AllowAny,]
    # parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Handle the creation of a Product instance, ensuring the request is made by a Vendor.
        The function checks the user's role and vendor profile, processes nested data, 
        and associates the product with the vendor.
        """
        user = self.request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)
            
            if not vendor_obj:
                application_logger.error(f"Only vendors can create products for user {user.email}")
                raise PermissionDenied("Only vendors can create products.")
            
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(vendor=vendor_obj)
            product_instance = serializer.instance

            specifications_data = []
            colors_data = []
            sizes_data = []
            gallery_data = []
            for key, value in self.request.data.items():
                if key.startswith('specifications') and '[title]' in key:
                    index = key.split('[')[1].split(']')[0]
                    title = value
                    content_key = f'specifications[{index}][content]'
                    content = self.request.data.get(content_key)
                    specifications_data.append(
                        {'title': title, 'content': content})

                elif key.startswith('colors') and '[name]' in key:
                    index = key.split('[')[1].split(']')[0]
                    name = value
                    color_code_key = f'colors[{index}][color_code]'
                    color_code = self.request.data.get(color_code_key)
                    image_key = f'colors[{index}][image]'
                    image = self.request.data.get(image_key)
                    colors_data.append(
                        {'name': name, 'color_code': color_code, 'image': image})

                elif key.startswith('sizes') and '[name]' in key:
                    index = key.split('[')[1].split(']')[0]
                    name = value
                    price_key = f'sizes[{index}][price]'
                    price = self.request.data.get(price_key)
                    sizes_data.append({'name': name, 'price': price})

                elif key.startswith('gallery') and '[image]' in key:
                    index = key.split('[')[1].split(']')[0]
                    image = value
                    gallery_data.append({'image': image})

            # Log or print the data for debugging
            application_logger.info('specifications_data: %s', specifications_data)
            application_logger.info('colors_data: %s', colors_data)
            application_logger.info('sizes_data: %s', sizes_data)
            application_logger.info('gallery_data: %s', gallery_data)

            self.save_nested_data(
                product_instance, SpecificationSerializer, specifications_data)
            self.save_nested_data(product_instance, ColorSerializer, colors_data)
            self.save_nested_data(product_instance, SizeSerializer, sizes_data)
            self.save_nested_data(
                product_instance, GallerySerializer, gallery_data)

            application_logger.info(f"Product created by {user.email} with id {product_instance.id}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            application_logger.error(f"An error occurred while creating a product for user {user.email}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def save_nested_data(self, product_instance, serializer_class, data):
        serializer = serializer_class(data=data, many=True, context={
                                    'product_instance': product_instance})
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product_instance)

class ProductUpdateAPIView(generics.RetrieveUpdateAPIView):
    """
        API endpoint for vendors to update their product details.
        *   *URL:* /api/vendor/product-edit/<str:vendor_id>/<str:product_pid>/
        *   *Method:* PUT
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
        *   *Request Body (JSON):*
            json
                {
                "title": "Brand New Item",  // Vendor's product title
                "description": "This is a brand new item",  // Vendor's product description
                "category": [],  // Vendor's product category
                    "tags": "fashion, clothing",   // Vendor's product tags
                    "brand": "Gucci",   // Vendor's product brand
                    "price": 3000.00,   // Vendor's product price
                    "shipping_amount": 1000.00,   // Vendor's product shipping_amount
                    "stock_qty": 100,  // Vendor's product stock_qty
                    "image": "/media/uploads/product.png"   // Vendor's product image
                    "specifications[0][title]": "Made In",   // Vendor's product specification 1 title
                    "specifications[0][content]": "Nigeria",   // Vendor's product specification 1 content
                    "colors[0][name]": "Green",  // Vendor's product color 1 name
                    "colors[0][color_code]": "#00FF00",  // Vendor's product color 1 color_code
                    "sizes[0][name]": "M",  // Vendor's product size 1 name
                "sizes[0][price]": 1000.00,  // Vendor's product size 1 price
                "gallery[0][image]": "/media/uploads/gallery_image_1.png" // Vendor's product gallery 1 image
                }
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        {
                        "message": "Product Updated" // Success message
                        }
                    
                *   On failure (HTTP 400, 404 or 500):
                    json
                    {
                        "error": "Error message" // Error message explaining the failure
                    }
                    
                Possible error messages:
                * "You do not have permission to perform this action.": If the user is not a vendor.
                *  "Product not found": If product with the vendor_id and product_pid is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.

    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = (IsAuthenticated, )

    def get_object(self):
        """
            Override the default get_object method to retrieve a specific product for the authenticated vendor.
            """
        user = self.request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)

            vendor_id = self.kwargs['vendor_id']
            product_pid = self.kwargs['product_pid']
            try:
                vendor = Vendor.objects.get(id=vendor_id)
                product = Product.objects.get(vendor=vendor, pid=product_pid)
                vendor_is_owner(vendor_obj, obj=product)
                return product
            except (Vendor.DoesNotExist, Product.DoesNotExist):
                application_logger.error(f"Product with pid {product_pid} not found for vendor {user.email}")
                raise NotFound("Product not found")
        except Exception as e:
                application_logger.error(f"An unexpected error occurred while retrieving product with pid {self.kwargs['product_pid']}, {e}")
                return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            

        @transaction.atomic
        def update(self, request, *args, **kwargs):
            """
            Handle the update of a Product instance.
            The function checks the user's role and vendor profile, processes nested data, 
            and associates the product with the vendor.
            """
            try:
                product = self.get_object()

                # Deserialize product data
                serializer = self.get_serializer(product, data=request.data)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)

                # Delete all existing nested data
                product.specification().delete()
                product.color().delete()
                product.size().delete()
                product.gallery().delete()

                specifications_data = []
                colors_data = []
                sizes_data = []
                gallery_data = []
                # Loop through the keys of self.request.data
                for key, value in self.request.data.items():
                    # Example key: specifications[0][title]
                    if key.startswith('specifications') and '[title]' in key:
                        # Extract index from key
                        index = key.split('[')[1].split(']')[0]
                        title = value
                        content_key = f'specifications[{index}][content]'
                        content = self.request.data.get(content_key)
                        specifications_data.append(
                            {'title': title, 'content': content})

                    # Example key: colors[0][name]
                    elif key.startswith('colors') and '[name]' in key:
                        # Extract index from key
                        index = key.split('[')[1].split(']')[0]
                        name = value
                        color_code_key = f'colors[{index}][color_code]'
                        color_code = self.request.data.get(color_code_key)
                        image_key = f'colors[{index}][image]'
                        image = self.request.data.get(image_key)
                        colors_data.append(
                            {'name': name, 'color_code': color_code, 'image': image})

                    # Example key: sizes[0][name]
                    elif key.startswith('sizes') and '[name]' in key:
                        # Extract index from key
                        index = key.split('[')[1].split(']')[0]
                        name = value
                        price_key = f'sizes[{index}][price]'
                        price = self.request.data.get(price_key)
                        sizes_data.append({'name': name, 'price': price})

                    # Example key: gallery[0][image]
                    elif key.startswith('gallery') and '[image]' in key:
                        # Extract index from key
                        index = key.split('[')[1].split(']')[0]
                        image = value
                        gallery_data.append({'image': image})

                # Log or print the data for debugging
                application_logger.info('specifications_data: %s', specifications_data)
                application_logger.info('colors_data: %s', colors_data)
                application_logger.info('sizes_data: %s', sizes_data)
                application_logger.info('gallery_data: %s', gallery_data)

                # Save nested serializers with the product instance
                self.save_nested_data(
                    product, SpecificationSerializer, specifications_data)
                self.save_nested_data(product, ColorSerializer, colors_data)
                self.save_nested_data(product, SizeSerializer, sizes_data)
                self.save_nested_data(product, GallerySerializer, gallery_data)

                application_logger.info(f"Product with id {product.id} updated by user {request.user.email}")
                return Response({'message': 'Product Updated'}, status=status.HTTP_200_OK)
            except Exception as e:
                application_logger.error(f"An unexpected error occurred while updating product with pid {self.kwargs['product_pid']}, {e}")
                return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        def save_nested_data(self, product_instance, serializer_class, data):
            serializer = serializer_class(data=data, many=True, context={
                                        'product_instance': product_instance})
            serializer.is_valid(raise_exception=True)
            serializer.save(product=product_instance)

class ProductDeleteAPIView(generics.DestroyAPIView):
    """
        API endpoint for vendors to delete a product.
        *   *URL:* /api/vendor/product-delete/<str:vendor_id>/<str:product_pid>/
        *   *Method:* DELETE
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
    *   *Response (JSON):*
                *   On success (HTTP 204 No Content):
                        json
                        {}
                    
                *   On failure (HTTP 400, 404 or 500):
                    json
                    {
                        "error": "Error message" // Error message explaining the failure
                    }
                    
                Possible error messages:
                    * "You do not have permission to perform this action.": If the user is not a vendor.
                    *  "Product not found": If product with the vendor_id and product_pid is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = (IsAuthenticated, )

    def get_object(self):
        """
            Override the default get_object method to retrieve a specific product for the authenticated vendor.
            """
        user = self.request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)

            vendor_id = self.kwargs['vendor_id']
            product_pid = self.kwargs['product_pid']
            try:
                    vendor = Vendor.objects.get(id=vendor_id)
                    product = Product.objects.get(vendor=vendor, pid=product_pid)
                    vendor_is_owner(vendor_obj, obj=product)
                    return product
            except (Vendor.DoesNotExist, Product.DoesNotExist):
                application_logger.error(f"Product with pid {product_pid} not found for vendor {user.email}")
                raise NotFound("Product not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving product with pid {self.kwargs['product_pid']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        def destroy(self, request, *args, **kwargs):
            """
            Deletes the product object and returns a no content response on success or an error if any error occurs
            """
            try:
                product = self.get_object()
                application_logger.info(f"Product with pid {product.pid} deleted by vendor {request.user.email}")
                self.perform_destroy(product)
                return Response(status=status.HTTP_204_NO_CONTENT)
            except Exception as e:
                application_logger.error(f"An unexpected error occurred while deleting product with pid {self.kwargs['product_pid']}, {e}")
                return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FilterProductsAPIView(generics.ListAPIView):
    """
        API endpoint for filtering vendor products.
        *   *URL:* /api/vendor/product-filter/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *URL Parameter:* filter can be : published, draft, disabled, in-review, latest, oldest.
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
                            ...
                        ]
                    
                *   On failure (HTTP 404 or 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                    
                Possible Error Messages:
                    *  "Vendor not found": If vendor with id is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """
        Retrieves and filters the products based on the filter parameter using the vendor_id.
        """
        try:
            vendor_id = self.kwargs['vendor_id']
            filter = self.request.GET.get('filter')

            application_logger.info("filter ======== %s", filter)

            vendor = Vendor.objects.get(id=vendor_id)
            if filter == "published":
                products = Product.objects.filter(
                    vendor=vendor, status="published")
            elif filter == "draft":
                products = Product.objects.filter(vendor=vendor, status="draft")
            elif filter == "disabled":
                products = Product.objects.filter(vendor=vendor, status="disabled")
            elif filter == "in-review":
                products = Product.objects.filter(
                    vendor=vendor, status="in-review")
            elif filter == "latest":
                products = Product.objects.filter(vendor=vendor).order_by('-id')
            elif filter == "oldest":
                products = Product.objects.filter(vendor=vendor).order_by('id')
            else:
                products = Product.objects.filter(vendor=vendor)
            return products
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor with id {vendor_id} not found.")
            raise NotFound("Vendor not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving product with pid {self.kwargs['vendor_id']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request, *args, **kwargs):
        """
        Lists the serialized data.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while listing filtered products for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class Earning(generics.ListAPIView):
    """
        API endpoint for retrieving vendor earning details.
        *   *URL:* /api/vendor/earning/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        [
                            {
                            "monthly_revenue": 2000.00,
                            "total_revenue": 20000000.00
                        }
                        ]
                    
                *   On failure (HTTP 404 or 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                    
                Possible Error Messages:
                * "Vendor not found": If the vendor profile was not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = EarningSummarySerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """
        Retrieves monthly and total revenue of a vendor based on the provided id.
        """
        try:
            vendor_id = self.kwargs['vendor_id']
            vendor = Vendor.objects.get(id=vendor_id)

            one_month_ago = datetime.today() - timedelta(days=28)
            monthly_revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid", date__gte=one_month_ago).aggregate(
                total_revenue=Sum(F('sub_total') + F('shipping_amount')))['total_revenue'] or 0
            total_revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid").aggregate(
                total_revenue=Sum(F('sub_total') + F('shipping_amount')))['total_revenue'] or 0

            return [{
                'monthly_revenue': monthly_revenue,
                'total_revenue': total_revenue,
            }]
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor with id {vendor_id} not found.")
            raise NotFound("Vendor not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving Earning details for vendor with id {vendor_id}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def list(self, request, *args, **kwargs):
        """
        Lists the serialized data.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while listing earning details for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(('GET',))
def MonthlyEarningTracker(request, vendor_id):
    """
    API endpoint for retrieving monthly earning tracker for a specific vendor.
        *   *URL:* /api/vendor/monthly-earning/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        [
                        {
                            "month": 1,
                            "sales_count": 2,
                            "total_earning": 10000.00
                            },
                                ...
                        ]
                    
                *   On failure (HTTP 404 or 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                    
                Possible Error Messages:
                * "Vendor not found": If the vendor profile was not found.
                    * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    try:
        vendor = Vendor.objects.get(id=vendor_id)
        monthly_earning_tracker = (
            CartOrderItem.objects
            .filter(vendor=vendor, order__payment_status="paid")
            .annotate(
                month=ExtractMonth("date")
            )
            .values("month")
            .annotate(
                sales_count=Sum("qty"),
                total_earning=Sum(
                    F('sub_total') + F('shipping_amount'))
            )
            .order_by("-month")
        )
        return Response(monthly_earning_tracker)
    except Vendor.DoesNotExist:
        application_logger.error(f"Vendor with id {vendor_id} not found.")
        return Response({'error': 'Vendor not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        application_logger.error(f"An unexpected error occurred while retrieving monthly earning tracker for vendor with id {vendor_id}, {e}")
        return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)












class ReviewsListAPIView(generics.ListAPIView):
    """
    API endpoint for retrieving a list of reviews for a particular vendor.
        *   *URL:* /api/vendor/reviews/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                    [
                            {
                            "id": "3a42df4c-b02b-4f62-ad50-7df09c3cb2d2",
                            "product":{
                            "id": "65f833d3-51b7-40ae-a448-9393e952668c",
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
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                    
                Possible Error Messages:
                    * "Vendor not found": If vendor with id is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = ReviewSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """
            Retrieves all review that are associated to the products of the vendor using the vendor_id.
            """
        try:
                vendor_id = self.kwargs['vendor_id']
                vendor = Vendor.objects.get(id=vendor_id)
                reviews = Review.objects.filter(product__vendor=vendor).select_related('product', 'profile__user')
                return reviews
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor with id {vendor_id} not found.")
            raise NotFound("Vendor not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving reviews for vendor with id {vendor_id}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def list(self, request, *args, **kwargs):
        """
        Lists the serialized data.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while listing reviews for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ReviewsDetailAPIView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for retrieving, updating a specific review for a particular vendor.
        *   *URL:* /api/vendor/reviews/<str:vendor_id>/<str:review_id>/
        *   *Method:* GET, PUT
        *   *Authentication:* Requires a valid authentication token in the Authorization header for PUT requests.
        *   *Request Body (JSON for PUT):*
            json
                {
                "rating": 5,
                "review": "A Very Good Product."
                }
        *   *Response (JSON):*
                *   On success (HTTP 200 OK for GET and PUT):
                            json
                            {
                            "id": "3a42df4c-b02b-4f62-ad50-7df09c3cb2d2",
                            "product":{
                                "id": "65f833d3-51b7-40ae-a448-9393e952668c",
                                ...
                                },
                                "profile": {
                                "id": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                                ...
                                },
                            "rating": 5,
                            "review": "Good Product"
                            }
                        
                *   On failure (HTTP 400, 404 or 500):
                    json
                    {
                        "error": "Error message" // Error message detailing the failure
                    }
                    
                Possible error messages:
                *  "You do not have permission to perform this action.": If the user is not the owner of the review.
                    *  "Review not found": If review with the vendor_id and review_id is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = ReviewSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        """
            Override the default get_object method to retrieve a specific review for the authenticated vendor.
            """
        user = self.request.user
        try:
                vendor_obj = fetch_user_and_vendor(user)
                vendor_is_owner(vendor_obj, obj=self.request.user)

                vendor_id = self.kwargs['vendor_id']
                review_id = self.kwargs['review_id']
                try:
                    vendor = Vendor.objects.get(id=vendor_id)
                    review = Review.objects.get(product__vendor=vendor, id=review_id)
                    vendor_is_owner(vendor_obj, obj=review)
                    return review
                except (Vendor.DoesNotExist, Review.DoesNotExist):
                    application_logger.error(f"Review with id {review_id} not found for vendor {user.email}")
                    raise NotFound("Review not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving review with id {self.kwargs['review_id']}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        def retrieve(self, request, *args, **kwargs):
            """
            Returns the serialized review data.
            """
            try:
                instance = self.get_object()
                serializer = self.get_serializer(instance)
                return Response(serializer.data, status=status.HTTP_200_OK)
            except Exception as e:
                application_logger.error(f"An unexpected error occurred while retrieving review details {self.kwargs['review_id']}, {e}")
                return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        """
        Updates the review object and returns a no content response on success or an error if any error occurs
        """
        try:
            review = self.get_object()
            serializer = self.get_serializer(review, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            application_logger.info(f"Review with id {review.id} updated by user {request.user.email}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while updating review with id {self.kwargs['review_id']}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CouponListAPIView(generics.ListAPIView):
    """
    API endpoint for retrieving a list of coupons for a particular vendor.
        *   *URL:* /api/vendor/coupon-list/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                    [
                        {
                        "id": "96609158-5597-465b-903e-85f35e4289d9",
                            "vendor": "ee82962d-6116-49eb-ac26-c76723e87d85",
                            "code": "DISCOUNT_CODE",
                            "discount": 10,
                            "active": true,
                            "date": "2024-07-29T15:39:14.964109+00:00"
                            },
                            ...
                        ]
                    
                *   On failure (HTTP 400, 404 or 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                    
                Possible Error Messages:
                * "You do not have permission to perform this action.": If the user is not a vendor.
                * "Vendor not found": If vendor with id is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = CouponSerializer
    permission_classes = (IsAuthenticated, )

    def get_queryset(self):
        """
        Retrieves a list of coupons that are associated with the authenticated vendor.
        """
        user = self.request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)
            coupon = Coupon.objects.filter(vendor=vendor_obj)
            return coupon
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving coupons for a vendor, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        def list(self, request, *args, **kwargs):
            """
            Lists the serialized data.
            """
            try:
                queryset = self.get_queryset()
                serializer = self.get_serializer(queryset, many=True)
                return Response(serializer.data)
            except Exception as e:
                application_logger.error(f"An unexpected error occurred while listing coupons for a vendor, {e}")
                return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CouponCreateAPIView(generics.CreateAPIView):
    """
    API endpoint for vendors to create a new coupon.
        *   *URL:* /api/vendor/coupon-create/<str:vendor_id>/
        *   *Method:* POST
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
        *   *Request Body (JSON):*
                json
                {
                "code": "DISCOUNT_CODE", // Vendor's coupon code
                "discount": 10, // Vendor's discount amount
                "active": true // Vendor's coupon status
                }
        *   *Response (JSON):*
                *   On success (HTTP 201 Created):
                        json
                        {
                            "message": "Coupon Created Successfully.", // Success message
                            "id": "96609158-5597-465b-903e-85f35e4289d9",
                            "vendor": "ee82962d-6116-49eb-ac26-c76723e87d85",
                            "code": "DISCOUNT_CODE",
                            "discount": 10,
                            "active": true,
                            "date": "2024-07-29T15:39:14.964109+00:00"
                        }
                    
                *   On failure (HTTP 400, 404 or 500):
                    json
                    {
                        "error": "Error message" // Error message explaining the failure
                    }
                    
                Possible error messages:
                    * "You do not have permission to perform this action.": If the user is not a vendor
                *   "Vendor not found": If vendor with id is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = CouponSerializer
    queryset = Coupon.objects.all()
    permission_classes = (IsAuthenticated, )

    def create(self, request, *args, **kwargs):
        """
        Handle the creation of a new Coupon instance, ensuring the request is made by a Vendor.
        """
        user = request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)

            payload = request.data
            code = payload['code']
            discount = payload['discount']
            active = payload['active']

            application_logger.info("vendor_id ======== %s", vendor_obj.id)
            application_logger.info("code ======== %s", code)
            application_logger.info("discount ======== %s", discount)
            application_logger.info("active ======== %s", active)

        
            coupon = Coupon.objects.create(
                vendor=vendor_obj,
                code=code,
                discount=discount,
                active=(active.lower() == "true")
            )
            application_logger.info(f"Coupon created by {user.email} with id: {coupon.id}")
            serializer = self.get_serializer(coupon)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            application_logger.error(f"An unexpected error occurred while creating coupon for vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CouponDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API endpoint for retrieving, updating and deleting coupon for a particular vendor.
        *   *URL:* /api/vendor/coupon-detail/<str:vendor_id>/<str:coupon_id>/
        *   *Method:* GET, PUT, DELETE
        *   *Authentication:* Requires a valid authentication token in the Authorization header for PUT and DELETE requests.
        *   *Request Body (JSON for PUT):*
                json
                {
                "code": "DISCOUNT_CODE", // Vendor's coupon code
                "discount": 10, // Vendor's discount amount
                "active": true // Vendor's coupon status
                }
        *   *Response (JSON):*
            *   On success (HTTP 200 OK for GET and PUT, 204 for DELETE):
                        json
                        {
                        "id": "96609158-5597-465b-903e-85f35e4289d9",
                            "vendor": "ee82962d-6116-49eb-ac26-c76723e87d85",
                            "code": "DISCOUNT_CODE",
                            "discount": 10,
                            "active": true,
                            "date": "2024-07-29T15:39:14.964109+00:00"
                        }
                    
                *   On failure (HTTP 400, 404 or 500):
                    json
                    {
                        "error": "Error message" // Error message explaining the failure
                    }
                    
                Possible error messages:
                    * "You do not have permission to perform this action.": If the user is not the owner of the coupon.
                * "Coupon not found": If coupon with the vendor_id and coupon_id is not found.
                *   "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = CouponSerializer
    permission_classes = (IsAuthenticated, )

    def get_object(self):
        """
        Override the default get_object method to retrieve a specific coupon for the authenticated vendor.
        """
        user = self.request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)
        
            vendor_id = self.kwargs['vendor_id']
            coupon_id = self.kwargs['coupon_id']
            try:
                vendor = Vendor.objects.get(id=vendor_id)
                coupon = Coupon.objects.get(vendor=vendor, id=coupon_id)
                vendor_is_owner(vendor_obj, obj=coupon)
                return coupon
            except (Vendor.DoesNotExist, Coupon.DoesNotExist):
                application_logger.error(f"Coupon with id {coupon_id} not found for vendor {user.email}")
                raise NotFound("Coupon not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving coupon with id {self.kwargs['coupon_id']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def retrieve(self, request, *args, **kwargs):
        """
        Returns the serialized coupon data.
        """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving coupon details with id {self.kwargs['coupon_id']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        """
        Updates the coupon object and returns a no content response on success or an error if any error occurs
        """
        try:
            coupon = self.get_object()
            serializer = self.get_serializer(coupon, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            application_logger.info(f"Coupon with id {coupon.id} updated by vendor {request.user.email}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while updating coupon with id {self.kwargs['coupon_id']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

    def destroy(self, request, *args, **kwargs):
        """
        Deletes the coupon object and returns a no content response on success or an error if any error occurs
        """
        try:
            coupon = self.get_object()
            self.perform_destroy(coupon)
            application_logger.info(f"Coupon with id {coupon.id} deleted by vendor {request.user.email}")
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while deleting coupon with id {self.kwargs['coupon_id']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CouponStats(generics.ListAPIView):
    """
    API endpoint for retrieving coupon statistics for a particular vendor.
        *   *URL:* /api/vendor/coupon-stats/<str:vendor_id>/
        *   *Method:* GET
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                    [
                            {
                            "total_coupons": 5,
                            "active_coupons": 2
                            }
                        ]
                    
                *   On failure (HTTP 400, 404 or 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                    
                Possible Error Messages:
                * "You do not have permission to perform this action.": If the user is not a vendor.
                * "Vendor not found": If vendor with id is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = CouponSummarySerializer
    permission_classes = (IsAuthenticated, )

    def get_queryset(self):
        """
        Retrieves and returns the total_coupons and active_coupons associated with the vendor
        """
        user = self.request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)

            total_coupons = Coupon.objects.filter(vendor=vendor_obj).count()
            active_coupons = Coupon.objects.filter(
                vendor=vendor_obj, active=True).count()

            return [{
                'total_coupons': total_coupons,
                'active_coupons': active_coupons,
            }]
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving coupon stats for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request, *args, **kwargs):
        """
            Lists the serialized data.
            """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while listing coupon stats for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VendorProfileUpdateView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for updating vendor profile settings.
        *   *URL:* /api/vendor/settings/<str:pk>/
        *   *Method:* GET, PUT
        *   *Authentication:* Requires a valid authentication token in the Authorization header for PUT requests.
        *   *Request Body (JSON for PUT):*
            json
            {
                "phone": "08011111111",  // Vendor's phone number
                "address": "Some Location",   // Vendor's address
                "city": "Some city", //Vendor's city
                "state": "Some state", //Vendor's state
                "country": "Some Country", //Vendor's country
                "image": "/media/uploads/image_profile.png" //Vendor's profile image
                }
            
        *   *Response (JSON):*
                *   On success (HTTP 200 OK for GET and PUT):
                        json
                        {
                            "id": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                            "user": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                            "phone": "08011111111",
                            "address": "Some Location",
                            "city": "Some city",
                            "state": "Some state",
                            "country": "Some Country",
                            "image": "/media/uploads/image_profile.png"
                        }
                    
                *   On failure (HTTP 400, 404 or 500):
                    json
                    {
                        "error": "Error message" // Error message explaining the failure
                    }
                Possible Error Messages:
                * "You do not have permission to perform this action.": If the user is not a vendor
                *  "Profile not found": If profile with pk is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    queryset =  Product.objects.all()
    serializer_class =  ProfileSerializer
    permission_classes = (IsAuthenticated, )

    def get_object(self):
        """
        Override the default get_object method to retrieve a specific profile for the authenticated vendor.
        """
        user = self.request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)
            try:
                profile = user.profile
                vendor_is_owner(vendor_obj, obj=profile)
                return profile
            except  Exception as e:
                application_logger.error(f"Profile with id {self.kwargs['pk']} not found for vendor {user.email}")
                raise NotFound("Profile not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving Profile with id {self.kwargs['pk']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        """
        Returns the serialized profile data.
        """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving profile settings with id {self.kwargs['pk']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        """
        Updates the profile object and returns a no content response on success or an error if any error occurs
        """
        try:
            profile = self.get_object()
            serializer = self.get_serializer(profile, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            application_logger.info(f"Profile with id {profile.id} updated by user {request.user.email}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while updating profile settings with id {self.kwargs['pk']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ShopUpdateView(generics.RetrieveUpdateAPIView):
    """
        API endpoint for updating shop settings.
        *   *URL:* /api/vendor/shop-settings/<str:pk>/
        *   *Method:* GET, PUT
        *   *Authentication:* Requires a valid authentication token in the Authorization header for PUT requests.
        *   *Request Body (JSON for PUT):*
            json
                {
                "name": "My Fashion Shop",  // Vendor's shop name
                "email": "vendor@email.com",  // Vendor's email
                "description": "This is my brand new shop", // Vendor's shop description
                "mobile": "08011111111", //Vendor's mobile number
                "image": "/media/uploads/shop_image.png" //Vendor's shop image
                }
        *   *Response (JSON):*
                *   On success (HTTP 200 OK for GET and PUT):
                        json
                        {
                            "id": "ee82962d-6116-49eb-ac26-c76723e87d85",
                            "user": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                            "image": null,
                            "name": "AL-FASHIONISTARCLOTHINGS LIMITED",
                            "email": "alfashionistar@gmail.com",
                            "description": "We sells Quality Wears.",
                            "mobile": "08097888888",
                            "verified": true,
                            "active": true,
                            "wallet_balance": 0.00,
                            "vid": "bckgndnmlr",
                            "date": "2024-07-29T15:39:14.964109+00:00",
                            "slug": "al-fashionistarclothings-limited-b4x8",
                            "transaction_password": "1234"
                            }
                    
                *   On failure (HTTP 400, 404 or 500):
                    json
                    {
                        "error": "Error message" // Error message explaining the failure
                    }
                    
                Possible error messages:
                    * "You do not have permission to perform this action.": If the user is not a vendor
                    *  "Vendor not found": If shop with pk is not found.
                    * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.

    """
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = (IsAuthenticated, )      
    
    def get_object(self):
        """
        Override the default get_object method to retrieve a specific vendor profile for the authenticated vendor.
        """
        user = self.request.user
        try:
            vendor_obj = fetch_user_and_vendor(user)
            vendor_is_owner(vendor_obj, obj=self.request.user)
            try:
                vendor = Vendor.objects.get(id=self.kwargs['pk'])
                vendor_is_owner(vendor_obj, obj=vendor)
                return vendor
            except Vendor.DoesNotExist:
                application_logger.error(f"Vendor with id {self.kwargs['pk']} not found for user {user.email}")
                raise NotFound("Vendor not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving shop settings with id {self.kwargs['pk']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        """
            Returns the serialized vendor data.
            """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving shop settings with id {self.kwargs['pk']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

    def update(self, request, *args, **kwargs):
        """
        Updates the vendor object and returns a no content response on success or an error if any error occurs
        """
        try:
            vendor = self.get_object()
            serializer = self.get_serializer(vendor, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            application_logger.info(f"Shop with id {vendor.id} updated by user {request.user.email}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while updating shop settings with id {self.kwargs['pk']}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)









class ShopAPIView(generics.RetrieveAPIView):
    """
    API endpoint to retrieve details of a specific shop.
    *   *URL:* /api/shop/<str:vendor_slug>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        {
                            "id": "ee82962d-6116-49eb-ac26-c76723e87d85",
                            "user": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                            "image": null,
                            "name": "AL-FASHIONISTARCLOTHINGS LIMITED",
                            "email": "alfashionistar@gmail.com",
                            "description": "We sells Quality Wears.",
                            "mobile": "08097888888",
                            "verified": true,
                            "active": true,
                            "wallet_balance": 0.00,
                            "vid": "bckgndnmlr",
                            "date": "2024-07-29T15:39:14.964109+00:00",
                            "slug": "al-fashionistarclothings-limited-b4x8",
                            "transaction_password": "1234"
                        }
                    
                *   On failure (HTTP 404 or 500):
                    json
                    {
                        "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                    }
                Possible Error Messages:
                *  "Vendor not found": If the shop with the vendor_slug is not found
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    queryset = Product.objects.all()
    serializer_class = VendorSerializer
    permission_classes = (AllowAny, )

    def get_object(self):
        """
        Override the default get_object method to retrieve a specific vendor by the vendor_slug.
        """
        try:
            vendor_slug = self.kwargs['vendor_slug']

            vendor = Vendor.objects.get(slug=vendor_slug)
            return vendor
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor with slug {vendor_slug} not found.")
            raise NotFound("Vendor not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving shop details with slug {self.kwargs['vendor_slug']}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        """
        Returns the serialized vendor data.
        """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving shop details with slug {self.kwargs['vendor_slug']}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ShopProductsAPIView(generics.ListAPIView):
    """
    API endpoint to retrieve all products for a specific shop.
        *   *URL:* /api/vendor/products/<str:vendor_slug>/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
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
                                ...
                        ]
                    
                *   On failure (HTTP 404 or 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                Possible Error Messages:
                    *  "Vendor not found": If vendor with slug is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """
        Retrieves products for a vendor using the vendor_slug.
        """
        try:
            vendor_slug = self.kwargs['vendor_slug']
            vendor = Vendor.objects.get(slug=vendor_slug)
            products = Product.objects.filter(vendor=vendor)
            return products
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor with slug {vendor_slug} not found.")
            raise NotFound("Vendor not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving product with slug {self.kwargs['vendor_slug']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request, *args, **kwargs):
        """
        Lists the serialized data.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while listing products for a vendor, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VendorRegister(generics.CreateAPIView):
    """
    API endpoint to create a new vendor profile
        *   *URL:* /api/vendor/register/
        *   *Method:* POST
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
        *   *Request Body (JSON):*
                json
                {
                    "name": "My Fashion Shop",  // Vendor's shop name
                    "email": "vendor@email.com",  // Vendor's email
                    "description": "This is my brand new shop", // Vendor's shop description
                    "mobile": "08011111111",  // Vendor's mobile number
                    "image": "/media/uploads/shop_image.png"   //Vendor's shop image
                }
        *   *Response (JSON):*
                *   On success (HTTP 201 Created):
                        json
                        {
                            "message": "Created vendor account",  // Success message
                            "vendor": {
                                    "store_name": "My Fashion Shop",
                                    "email": "vendor@email.com",
                                    "phone_number": "08011111111",
                                    "description": "This is my brand new shop"
                                }
                        }
                *   On failure (HTTP 400 or 500):
                    json
                    {
                        "error": "Error message" // Error message explaining the failure
                    }
                    
                Possible Error Messages:
                * "User is not authenticated": If the user is not authenticated.
                *  "Name, email, and mobile are required fields.": if name, email and mobile were not provided
                * "A vendor profile already exists for this user.": if the user already has a vendor profile.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.

    """
    serializer_class = VendorSerializer
    queryset = Vendor.objects.all()
    permission_classes = [IsAuthenticated]  # Ensure the user is logged in

    def create(self, request, *args, **kwargs):
        """
        Handles the creation of a new Vendor instance.
        """
        try:
            # Ensure the user is attached
            user = request.user  # The logged-in user
            
            if not user:
                return Response({'error': 'User is not authenticated'}, status=status.HTTP_400_BAD_REQUEST)

            
            try:
                user_obj = User.objects.get(pk=user.pk)
            except User.DoesNotExist:
                application_logger.error(f"User with id {user.pk} does not exist")
                return None,  "User not found"

            if user_obj.role != 'vendor':
                application_logger.error(f"User: {user_obj.email} is not a vendor")
                return Response({'error': "User Role is not Set To 'VENDOR' "}, status=status.HTTP_400_BAD_REQUEST)

            
            
            # Create a new dictionary that includes user ID
            payload = request.data.copy()  # Make a mutable copy of request.data
            payload['user'] = user.id  # Attach the authenticated user to the request data

            # Now, call the serializer to create the vendor
            serializer = self.get_serializer(data=payload)
            
            if serializer.is_valid():
                vendor = serializer.save()
                vendor_data = {
                    'store_name': vendor.name,
                    'email': vendor.email,
                    'phone_number': vendor.mobile,
                    'description': vendor.description,
                }
                application_logger.info(f"Vendor profile created successfully for user: {user.email} with id {vendor.id}")
                return Response({"message": "Created vendor account", "vendor": vendor_data}, status=status.HTTP_201_CREATED)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while creating vendor profile for user {user.email}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    
class VendorStoreView(generics.ListAPIView):
    """
    API endpoint to retrieve all products for a specific vendor along with vendor details.
        *   *URL:* /api/vendor/<str:vendor_id>/store/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                        {
                        "store_name": "My Fashion Shop",
                            "phone_number": "08011111111",
                            "address": "Some Location",
                            "products":
                                [
                                    {
                                    "id": "96609158-5597-465b-903e-85f35e4289d9",
                                    "title": "Socks",
                                    "image": null,
                                    "description": "Brand New Socks",
                                    ...
                                    },
                                    ...
                                ]
                        }
                    
                *   On failure (HTTP 404 or 500):
                    json
                    {
                        "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                    }
                Possible Error Messages:
                    *  "Vendor not found": If vendor with id is not found.
                * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to retrieve vendor's store information and associated products.
        """
        try:
            vendor_id = self.kwargs['vendor_id']
            vendor = Vendor.objects.get(id=vendor_id)
            products = Product.objects.filter(vendor=vendor).order_by('title')
            
            product_serializer = self.get_serializer(products, many=True)

            vendor_data = {
                'store_name': vendor.name,  
                'phone_number': vendor.user.phone,
                'address': vendor.user.profile.address,
                'products': product_serializer.data
            }
            
            return Response(vendor_data, status=status.HTTP_200_OK)
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor with id {self.kwargs['vendor_id']} not found.")
            raise NotFound("Vendor not found")
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving vendor store details with id {self.kwargs['vendor_id']}, {e}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AllVendorsProductsList(generics.ListAPIView):
    """
    API endpoint to retrieve all verified vendors with their products.
        *   *URL:* /api/vendors/
        *   *Method:* GET
        *   *Authentication:* No authentication required, viewable by all.
        *   *Request Body:* None
        *   *Response (JSON):*
                *   On success (HTTP 200 OK):
                        json
                    {
                            "total_verified_vendors": 20,
                            "vendors":
                            [
                            {
                                "name": "My Fashion Shop",
                                "image": "/media/uploads/shop_image.png",
                                "average_rating": 4.7,
                                "phone": "08011111111",
                                "address": "Some Location",
                                "slug": "my-fashion-shop-b4x8"
                                },
                                ...
                                ]
                        }
                    
                *   On failure (HTTP 500):
                    json
                        {
                            "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                        }
                Possible Error Messages:
                    * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    serializer_class = AllVendorSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        """
        Retrieves all the verified vendors.
        """
        return Vendor.objects.filter(verified=True).select_related('user', 'user__profile')

    def list(self, request, *args, **kwargs):
        """
        Returns a json response of the list of serialized verified vendors.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            total_verified_vendors = queryset.count()
            return Response({
                'total_verified_vendors': total_verified_vendors,
                'vendors': serializer.data
            })
        except Exception as e:
                application_logger.error(f"An unexpected error occurred while retrieving all verified vendors, {e}")
                return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class VENDORListView(generics.ListAPIView):
    serializer_class = AllVENDORSerializer
    queryset = Vendor.objects.all()
    permission_classes = (AllowAny,)
















