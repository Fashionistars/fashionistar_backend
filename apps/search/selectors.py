# apps/search/selectors.py
"""
Fashionistar — Search App Selectors.
Provides read-only database queries for the search domain.
"""
from django.db.models import QuerySet
from .models import SearchableContent, SearchQuery, SearchResult

def get_searchable_content_queryset() -> QuerySet:
    """Retrieve all searchable content objects."""
    return SearchableContent.objects.all()

def get_search_queries_queryset() -> QuerySet:
    """Retrieve all logged search queries."""
    return SearchQuery.objects.all()

def get_search_results_queryset() -> QuerySet:
    """Retrieve all cached search results."""
    return SearchResult.objects.all()
