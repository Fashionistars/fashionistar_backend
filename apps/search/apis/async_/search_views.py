# apps/search/apis/async_/search_views.py
"""
Django-Ninja async views for the search domain (reads/GETs).
"""

from typing import List, Dict, Any, Optional
from ninja import Router, Schema
from django.utils import timezone
from django.db.models import Avg

from ...services import HybridSearchService
from ...models import SearchQuery as SearchQueryModel

router = Router(tags=["search"])


class SearchResultSchema(Schema):
    id: int
    encounter_id: Optional[int] = None
    content_type: str
    content_id: int
    title: str
    snippet: str
    combined_score: float = 0.0
    search_type: str
    metadata: Dict[str, Any] = {}


class PaginationSchema(Schema):
    page: int
    page_size: int
    total_pages: int
    total_results: int
    has_next: bool
    has_previous: bool


class SearchResponseSchema(Schema):
    query: str
    filters: Dict[str, Any]
    results: List[SearchResultSchema]
    pagination: PaginationSchema
    execution_time_ms: int
    search_id: int


class SuggestionResponseSchema(Schema):
    query_prefix: str
    suggestions: List[str]


class AnalyticsResponseSchema(Schema):
    since_days: int
    total_queries: int
    average_execution_time_ms: int


@router.get("/content/", response=SearchResponseSchema)
async def search_content(
    request,
    q: str,
    encounter_id: Optional[int] = None,
    content_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    """Perform async hybrid search on all clinical and notes content."""
    filters = {}
    if encounter_id:
        filters['encounter_id'] = encounter_id
    if content_type:
        filters['content_type'] = [content_type]
    if date_from:
        filters['date_from'] = date_from
    if date_to:
        filters['date_to'] = date_to

    page_size = min(page_size, 100)

    search_service = HybridSearchService()
    search_results = await search_service.asearch(
        query_text=q,
        user=request.auth,
        filters=filters,
        limit=page_size * 5
    )

    results_list = search_results['results']
    total_results = len(results_list)
    total_pages = (total_results + page_size - 1) // page_size if total_results else 1
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_results = results_list[start_idx:end_idx]

    return {
        "query": q,
        "filters": filters,
        "results": paginated_results,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_results": total_results,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
        "execution_time_ms": search_results['execution_time_ms'],
        "search_id": search_results['search_id']
    }


@router.get("/suggestions/", response=SuggestionResponseSchema)
async def search_suggestions(request, q: str, limit: int = 10):
    """Provide async search suggestions based on previous successful query history."""
    if len(q) < 2:
        return {"query_prefix": q, "suggestions": []}
    
    limit = min(limit, 20)
    
    suggestions_qs = SearchQueryModel.objects.filter(
        query_text__icontains=q,
        results_count__gt=0
    ).values('query_text').distinct().order_by('-id')[:limit]
    
    suggestions = [s['query_text'] async for s in suggestions_qs]
    
    return {
        "query_prefix": q,
        "suggestions": suggestions
    }


@router.get("/analytics/", response=AnalyticsResponseSchema)
async def search_analytics(request, days: int = 30):
    """Fetch search analytics and average execution speeds asynchronously."""
    days = min(max(days, 1), 365)
    since = timezone.now() - timezone.timedelta(days=days)
    qs = SearchQueryModel.objects.filter(created_at__gte=since)
    
    total = await qs.acount()
    if total:
        agg = await qs.aaggregate(models_avg=Avg('execution_time_ms'))
        avg_time = agg['models_avg']
    else:
        avg_time = 0
        
    return {
        "since_days": days,
        "total_queries": total,
        "average_execution_time_ms": int(avg_time or 0),
    }
