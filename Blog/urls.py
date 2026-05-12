from django.urls import path
from Blog.views import BlogListView, BlogDetailView, BlogCreateView, BlogUpdateView, BlogDeleteView

urlpatterns = [
    path('blogs/', BlogListView.as_view(), name='blog-list'),
    path('blogs/<int:pk>/', BlogDetailView.as_view(), name='blog-detail'),
    path('blogs/create/', BlogCreateView.as_view(), name='blog-create'),
    path('blogs/update/<int:pk>/', BlogUpdateView.as_view(), name='blog-update'),
    path('blogs/delete/<int:pk>/', BlogDeleteView.as_view(), name='blog-delete'),
]
