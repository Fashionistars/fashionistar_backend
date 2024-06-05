# views.py

from rest_framework import viewsets, status, parsers
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Collections
from .serializers import CollectionsSerializer

class CollectionsViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing Collection instances.
    """
    queryset = Collections.objects.all()
    serializer_class = CollectionsSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser)

    def create(self, request, *args, **kwargs):
        """
        Create a new Collection instance.
        
        Args:
            request: The request object containing data for the new instance.
        
        Returns:
            Response: The response object containing the created instance data.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """
        Update an existing Collection instance.
        
        Args:
            request: The request object containing data for the update.
        
        Returns:
            Response: The response object containing the updated instance data.
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """
        Delete an existing Collection instance.
        
        Args:
            request: The request object.
        
        Returns:
            Response: The response object indicating the deletion status.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"message": "Image deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
