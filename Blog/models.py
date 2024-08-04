from django.db import models
from userauths.models import User

class Blog(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='media/blog_images/')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    gallery_images = models.ManyToManyField('BlogGallery', blank=True, related_name='blogs')

    def __str__(self):
        return self.title

class BlogGallery(models.Model):
    image = models.ImageField(upload_to='media/blog_gallery_images/', blank=True, null=True)

    def __str__(self):
        return f"Gallery image {self.id}"
