# apps/search/selectors/search_selectors.py
"""
Read-only data fetching layer for Search domain.
Follows vendor pattern with sync and async dual methods.
"""

import asyncio
from typing import Optional, List
from apps.search.models import SearchableContent, SearchQuery, SearchResult


# ============================================================================
# SYNC SELECTORS (for DRF)
# ============================================================================

def get_searchable_content(content_type: str = None, encounter_id: int = None, limit: int = 100):
    """Get searchable content (sync)."""
    queryset = SearchableContent.objects.all()
    if content_type:
        queryset = queryset.filter(content_type=content_type)
    if encounter_id:
        queryset = queryset.filter(encounter_id=encounter_id)
    return list(queryset.order_by('-created_at')[:limit])


def get_search_queries(user_id: str = None, limit: int = 10):
    """Get search queries (sync)."""
    queryset = SearchQuery.objects.all()
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    return list(queryset.order_by('-created_at')[:limit])


def get_cached_results(query_id: int):
    """Get cached search results (sync)."""
    return list(SearchResult.objects.filter(query_id=query_id).order_by('rank'))


# ============================================================================
# ASYNC SELECTORS (for Django Ninja)
# ============================================================================

async def aget_searchable_content(content_type: str = None, encounter_id: int = None, limit: int = 100):
    """Get searchable content (async)."""
    queryset = SearchableContent.objects.all()
    if content_type:
        queryset = queryset.filter(content_type=content_type)
    if encounter_id:
        queryset = queryset.filter(encounter_id=encounter_id)
    return [c async for c in queryset.order_by('-created_at')[:limit]]


async def aget_search_queries(user_id: str = None, limit: int = 10):
    """Get search queries (async)."""
    queryset = SearchQuery.objects.all()
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    return [q async for q in queryset.order_by('-created_at')[:limit]]


async def aget_cached_results(query_id: int):
    """Get cached search results (async)."""
    queryset = SearchResult.objects.filter(query_id=query_id).order_by('rank')
    return [r async for r in queryset]


# ============================================================================
# PARALLEL LOADING (async only)
# ============================================================================

async def aget_search_dashboard_parallel(user_id: str = None):
    """
    Load search dashboard data in parallel using asyncio.gather.
    Returns recent queries, content counts, and performance metrics.
    """
    from django.db.models import Count, Avg
    
    queries, content_count, avg_time = await asyncio.gather(
        aget_search_queries(user_id, 10),
        SearchableContent.objects.acount(),
        SearchQuery.objects.filter(user_id=user_id).aggregate(Avg('execution_time_ms')) if user_id else asyncio.sleep(0),
        return_exceptions=True,
    )
    
    return {
        'recent_queries': queries if not isinstance(queries, Exception) else [],
        'content_count': content_count if not isinstance(content_count, Exception) else 0,
        'avg_execution_time': avg_time if not isinstance(avg_time, Exception) else 0,
    }
