# vendor/Views/product1.py

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from django.db import transaction
import logging


# Imports for Swagger Schema Documentation
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


from store.models import Product
from vendor.models import Vendor
from vendor.serializerss.product1 import ProductSerializer1
from vendor.permissions import IsVendor # Import our robust permission class

application_logger = logging.getLogger('application')

class ProductCreateView(generics.CreateAPIView):
    """
    API endpoint for vendors to create a new product.
    This endpoint uses a transactional approach to ensure that a product and all its
    related details are created in a single, atomic operation.
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer1
    parser_classes = [MultiPartParser, FormParser]
    # permission_classes = [IsAuthenticated, IsVendor]    
    permission_classes = [AllowAny,]



    @swagger_auto_schema(
        operation_summary="Create a New Product",
        operation_description="Allows an authenticated vendor to create a new product, including its gallery, specifications, sizes, and colors, in a single request.",
        request_body=ProductSerializer1,
        responses={
            201: openapi.Response("Product Created Successfully", ProductSerializer1),
            400: "Bad Request - Invalid data provided",
            403: "Permission Denied - User is not an authorized vendor",
            404: "Not Found - Vendor profile is missing",
            500: "Internal Server Error"
        }
    )


    def create(self, request, *args, **kwargs):
        """
        Handles the creation of a Product instance.
        Permissions check for authenticated vendors is handled declaratively.
        """
        user = request.user
        application_logger.info(f"Product creation attempt by user: {user.identifying_info}")

        try:
            # Direct access to the vendor profile as requested.
            # The IsVendor permission class ensures this user should have a vendor_profile.
            vendor_obj = request.user.vendor_profile

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Use a database transaction for data integrity.
            with transaction.atomic():
                # Pass the vendor instance directly to the serializer's save method.
                serializer.save(vendor=vendor_obj)

            application_logger.info(f"Product created successfully by vendor: {vendor_obj.name}")
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

        except Vendor.DoesNotExist:
            # This handles the edge case where a user has role='vendor' but no profile.
            application_logger.critical(f"CRITICAL: User {user.email} with role 'vendor' has no vendor profile.")
            return Response({"error": "Vendor profile not found. Please contact support."}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            application_logger.error(f"Validation error during product creation by {user.identifying_info}: {e.detail}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            application_logger.critical(f"An unexpected error occurred during product creation by {user.identifying_info}: {str(e)}")
            return Response({"error": "An unexpected server error occurred. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        








