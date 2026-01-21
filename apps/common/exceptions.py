# apps/common/exceptions.py

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError, APIException, AuthenticationFailed, NotAuthenticated, PermissionDenied
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
import logging

logger = logging.getLogger('application')

def custom_exception_handler(exc, context):
    """
    Global exception handler for JSON-formatted error responses.
    Ensures that all API errors return a consistent structure:
    {
        "success": False,
        "message": "Error description",
        "code": "error_code",
        "errors": { ... } or [...]
    }
    """
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    # Handle standard Django exceptions that aren't caught by DRF
    if response is None:
        if isinstance(exc, DjangoValidationError):
            data = {"message": "Validation Error", "errors": exc.message_dict if hasattr(exc, 'message_dict') else exc.messages}
            response = Response(data, status=status.HTTP_400_BAD_REQUEST)
        elif isinstance(exc, Http404):
            data = {"message": "Not Found", "code": "not_found"}
            response = Response(data, status=status.HTTP_404_NOT_FOUND)
        elif isinstance(exc, DjangoPermissionDenied):
            data = {"message": "Permission Denied", "code": "permission_denied"}
            response = Response(data, status=status.HTTP_403_FORBIDDEN)
        else:
            # Catch-all for unhandled exceptions (500)
            logger.error(f"Unhandled Exception: {exc}", exc_info=True)
            data = {
                "message": "Internal Server Error",
                "code": "server_error",
                "detail": str(exc) # Consider masking this in production
            }
            return Response({
                "success": False,
                "message": "An unexpected error occurred.",
                "error": data
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if response is not None:
        # Standardize the response structure
        # If response.data is a list (e.g. from some validators), wrap it
        error_payload = response.data
        
        message = "Request failed"
        code = "error"
        
        if isinstance(exc, ValidationError):
            message = "Validation failed"
            code = "validation_error"
        elif isinstance(exc, AuthenticationFailed) or isinstance(exc, NotAuthenticated):
            message = "Authentication failed"
            code = "authentication_failed"
        elif isinstance(exc, PermissionDenied):
            message = "Permission denied"
            code = "permission_denied"
            
        # Refine payload to remove redundant keys if possible or just wrap it
        custom_response_data = {
            "success": False,
            "message": message,
            "code": code,
            "errors": error_payload
        }
        
        response.data = custom_response_data

    return response