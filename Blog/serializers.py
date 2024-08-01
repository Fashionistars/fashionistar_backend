from rest_framework import serializers
from Blog.models import Blog, BlogGallery

class BlogGallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogGallery
        fields = ['id', 'image']

class BlogSerializer(serializers.ModelSerializer):
    gallery_images = BlogGallerySerializer(many=True, read_only=True)

    class Meta:
        model = Blog
        fields = ['id', 'title', 'content', 'author', 'image', 'gallery_images', 'created_at', 'updated_at']
