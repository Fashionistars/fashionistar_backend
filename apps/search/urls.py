# apps/search/urls.py
"""
URL routes for the search app (DRF compatibility views).
"""

from django.urls import path
from .apis.sync import search_views

app_name = 'search'

urlpatterns = [
    path('content/', search_views.search_content, name='search-content'),
    path('suggestions/', search_views.search_suggestions, name='search-suggestions'),
    path('analytics/', search_views.search_analytics, name='search-analytics'),
]
