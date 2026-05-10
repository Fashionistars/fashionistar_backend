from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from Blog.models import Blog, BlogGallery
from Blog.serializers import BlogSerializer

class BlogListView(APIView):
    """
    View to retrieve all blog posts.
    """
    permission_classes = (AllowAny,)

    def get(self, request):
        try:
            blogs = Blog.objects.all()
            serializer = BlogSerializer(blogs, many=True)
            return Response({"message": "Blog posts retrieved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BlogDetailView(APIView):
    """
    View to retrieve a specific blog post by its ID.
    """
    permission_classes = (AllowAny,)

    def get(self, request, pk):
        try:
            blog = get_object_or_404(Blog, pk=pk)
            serializer = BlogSerializer(blog)
            return Response({"message": "Blog post retrieved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BlogCreateView(APIView):
    """
    View to handle POST requests for Blog.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            data = request.data
            serializer = BlogSerializer(data=data)
            if serializer.is_valid():
                blog = serializer.save(author=request.user)

                # Handle gallery images if provided
                gallery_images = request.FILES.getlist('gallery_images')
                for image in gallery_images:
                    blog_gallery = BlogGallery.objects.create(blog=blog, image=image)
                    blog.gallery_images.add(blog_gallery)

                blog.save()
                return Response({"message": "Blog post created successfully.", "data": serializer.data}, status=status.HTTP_201_CREATED)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BlogUpdateView(APIView):
    """
    View to handle PUT requests for Blog.
    """
    permission_classes = (IsAuthenticated,)

    def put(self, request, pk):
        try:
            blog = get_object_or_404(Blog, pk=pk, author=request.user)
            serializer = BlogSerializer(blog, data=request.data, partial=True)
            if serializer.is_valid():
                blog = serializer.save()

                # Handle gallery images if provided
                gallery_images = request.FILES.getlist('gallery_images')
                for image in gallery_images:
                    blog_gallery = BlogGallery.objects.create(blog=blog, image=image)
                    blog.gallery_images.add(blog_gallery)

                blog.save()
                return Response({"message": "Blog post updated successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BlogDeleteView(APIView):
    """
    View to handle DELETE requests for Blog.
    """
    permission_classes = (IsAuthenticated,)

    def delete(self, request, pk):
        try:
            blog = get_object_or_404(Blog, pk=pk, author=request.user)
            blog.delete()
            return Response({"message": "Blog post deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
