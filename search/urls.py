"""
URL های اپلیکیشن جستجو
"""

from django.urls import path
from . import views

app_name = 'search'

urlpatterns = [
    path('content/', views.search_content, name='search-content'),
    path('suggestions/', views.search_suggestions, name='search-suggestions'),
    path('analytics/', views.search_analytics, name='search-analytics'),
]

