# vendor/Views/product2.py

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
import logging

from store.models import Product
from vendor.models import Vendor
from vendor.permissions import IsVendor # Import our custom permission
from vendor.serializerss.product2 import *
# from vendor.serializerss.serializer2 import (
#     ProductCreateSerializer,
#     ProductListDetailSerializer
# )

application_logger = logging.getLogger('application')

class ProductCreateAPIView(generics.CreateAPIView):
    """
    API endpoint for an authenticated vendor to create a new product.
    Accepts multipart/form-data to handle image uploads.
    Nested data like specifications, sizes, and colors should be sent as JSON-encoded strings.
    """
    serializer_class = ProductCreateSerializer
    # permission_classes = [IsAuthenticated, IsVendor]
    permission_classes = [AllowAny,]

    # parser_classes = [MultiPartParser, FormParser]

    def get_serializer_context(self):
        """
        Pass gallery images from the request to the serializer context.
        """
        context = super().get_serializer_context()
        context['gallery_images'] = self.request.FILES.getlist('gallery_images')
        return context

    def perform_create(self, serializer):
        """
        Associate the newly created product with the logged-in vendor.
        """
        vendor = Vendor.objects.get(user=self.request.user)
        serializer.save(vendor=vendor)
        application_logger.info(f"Product '{serializer.instance.title}' created by vendor '{vendor.name}'.")

class ProductListAPIView(generics.ListAPIView):
    """
    API endpoint to list all products.
    Provides a detailed, nested view of each product for public consumption.
    """
    queryset = Product.objects.filter(status="published").order_by("-date")
    serializer_class = ProductListDetailSerializer
    permission_classes = [IsAuthenticated] # Or AllowAny if you want it public

class ProductDetailAPIView(generics.RetrieveAPIView):
    """
    API endpoint to retrieve the details of a single product.
    """
    queryset = Product.objects.filter(status="published")
    serializer_class = ProductListDetailSerializer
    permission_classes = [IsAuthenticated] # Or AllowAny
    lookup_field = 'pid' # Use the short UUID for lookups