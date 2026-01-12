from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger('application')

def custom_exception_handler(exc, context):
    """
    Global exception handler for JSON-formatted error responses.
    Handles both expected and unexpected exceptions with logging.
    
    Args:
        exc: The exception instance.
        context: The context dictionary.
        
    Returns:
        Response: A standardized JSON error response.
    """
    try:
        response = exception_handler(exc, context)

        if response is not None:
            response.data = {
                'success': False,
                'message': 'An error occurred',
                'error': response.data
            }
        else:
            response = Response({
                'success': False,
                'message': 'Internal server error',
                'error': str(exc)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.error(f"Exception handled: {str(exc)}")
        return response
    except Exception as e:
        logger.error(f"Error in exception handler: {str(e)}")
        return Response({
            'success': False,
            'message': 'Internal server error',
            'error': 'Exception handler failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
