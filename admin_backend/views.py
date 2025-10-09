from rest_framework import viewsets, status, parsers
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from admin_backend.models import Collections, Category, Brand
from admin_backend.serializers import CollectionsSerializer, CategorySerializer, BrandSerializer
from django.http import Http404





class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(active=True)
    permission_classes = (AllowAny,)


class CategoryCreateView(generics.CreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny,]

class BrandListView(generics.ListAPIView):
    serializer_class = BrandSerializer
    queryset = Brand.objects.filter(active=True)
    permission_classes = (AllowAny,)





class CollectionsViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing Collection instances.
    """
    queryset = Collections.objects.all()
    serializer_class = CollectionsSerializer
    permission_classes = [AllowAny]
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




class CategoryViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing CATEGORY instances.
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser)

    def get_object(self):
        """
        Override get_object to return the CATEGORY instance based on slug.
        """
        slug = self.kwargs.get('slug')
        try:
            return Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            raise Http404

    def create(self, request, *args, **kwargs):
        """
        Create a new CATEGORY instance.
        
        Args:
            request: The request object containing data for the new instance.
        
        Returns:
            Response: The response object containing the created instance data.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        created_instance = Category.objects.get(name=serializer.validated_data['name'])
    
        # Serialize the full instance
        full_serializer = self.get_serializer(created_instance)
        data = {
        'id': created_instance.id,
        'name': created_instance.name,
        'image': created_instance.image.url if created_instance.image else None,
        'slug': created_instance.slug,
        # 'createdAt': created_instance.createdAt,
        # 'updatedAt': created_instance.updatedAt,
        }
        # Create the response
        headers = self.get_success_headers(full_serializer.data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

        # headers = self.get_success_headers(serializer.data)
        # return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """
        Update an existing CATEGORY instance.
        
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
        Delete an existing CATEGORY instance.
        
        Args:
            request: The request object.
        
        Returns:
            Response: The response object indicating the deletion status.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"message": "Category deleted successfully"}, status=status.HTTP_204_NO_CONTENT)


class BrandViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing BRAND instances.
    """
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [AllowAny]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser)

    def create(self, request, *args, **kwargs):
        """
        Create a new BRAND instance.
        
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
        Update an existing BRAND instance.
        
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
        Delete an existing BRAND instance.
        
        Args:
            request: The request object.
        
        Returns:
            Response: The response object indicating the deletion status.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"message": "Image deleted successfully"}, status=status.HTTP_204_NO_CONTENT)

