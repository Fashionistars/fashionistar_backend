# apps/search/apis/async_/search_views.py
"""
Django Ninja async views for Search domain.
Follows vendor pattern with async endpoints under /api/v1/ninja/search/.
"""

from ninja import Router
from django.http import HttpRequest
from typing import List, Optional
from pydantic import BaseModel
from django.utils import timezone
from datetime import timedelta
from apps.search.selectors.search_selectors import (
    aget_searchable_content,
    aget_search_queries,
    aget_cached_results,
    aget_search_dashboard_parallel,
)
from apps.search.services import HybridSearchService
from apps.search.metrics import search_metrics
from apps.audit_logs.services.search.search_audit import SearchAuditService


router = Router(tags=['Search'])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class SearchRequest(BaseModel):
    query: str
    filters: Optional[dict] = None
    limit: int = 20
    boolean_mode: bool = True


class SearchResultItem(BaseModel):
    id: int
    title: str
    content: str
    snippet: str
    score: float
    combined_score: float


class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    total_count: int
    execution_time_ms: int
    query: str
    search_id: int


class DashboardResponse(BaseModel):
    recent_queries_count: int
    content_count: int
    avg_execution_time: float


class HealthCheckResponse(BaseModel):
    status: str
    index_status: str
    cache_status: str
    database_status: str
    content_count: int
    recent_queries_24h: int
    avg_execution_time_ms: float


# ============================================================================
# Async Endpoints
# ============================================================================

@router.post('/search/', response=SearchResponse)
async def execute_search(request: HttpRequest, search_request: SearchRequest):
    """
    Execute search query (async).
    Endpoint: POST /api/v1/ninja/search/search/
    """
    user = request.auth
    search_service = HybridSearchService()
    
    results = await search_service.asearch(
        query_text=search_request.query,
        user=user,
        filters=search_request.filters,
        limit=search_request.limit,
        boolean_mode=search_request.boolean_mode,
    )
    
    # Log audit events
    SearchAuditService.log_search_query_executed(
        actor=user,
        query_id=results.get('search_id'),
        query_text=search_request.query,
        filters=search_request.filters,
        request=request,
    )
    
    if results['total_count'] > 0:
        SearchAuditService.log_search_result_returned(
            actor=user,
            query_id=results.get('search_id'),
            result_count=results['total_count'],
            execution_time=results['execution_time_ms'],
            request=request,
        )
    else:
        SearchAuditService.log_search_zero_results(
            actor=user,
            query_id=results.get('search_id'),
            query_text=search_request.query,
            request=request,
        )
    
    return SearchResponse(
        results=[SearchResultItem(**r) for r in results['results']],
        total_count=results['total_count'],
        execution_time_ms=results['execution_time_ms'],
        query=results['query'],
        search_id=results['search_id'],
    )


@router.get('/dashboard/', response=DashboardResponse)
async def get_search_dashboard(request: HttpRequest):
    """
    Get search dashboard data in parallel (async).
    Endpoint: GET /api/v1/ninja/search/dashboard/
    """
    user = request.auth
    if not user:
        return DashboardResponse(recent_queries_count=0, content_count=0, avg_execution_time=0)
    
    dashboard_data = await aget_search_dashboard_parallel(str(user.id))
    
    return DashboardResponse(
        recent_queries_count=len(dashboard_data['recent_queries']),
        content_count=dashboard_data['content_count'],
        avg_execution_time=dashboard_data['avg_execution_time'],
    )


@router.get('/health/', response=HealthCheckResponse)
async def get_search_health(request: HttpRequest):
    """
    Get search service health check (async).
    Endpoint: GET /api/v1/ninja/search/health/
    """
    from apps.search.models import SearchableContent, SearchQuery
    from django.db.models import Count, Avg
    from django.core.cache import cache
    
    # Check database connectivity
    try:
        content_count = await SearchableContent.objects.acount()
        database_status = "healthy"
    except Exception:
        content_count = 0
        database_status = "unhealthy"
    
    # Check cache connectivity
    try:
        cache.set('search_health_check', 'ok', 10)
        cache.get('search_health_check')
        cache_status = "healthy"
    except Exception:
        cache_status = "unhealthy"
    
    # Check index status (content count > 0)
    index_status = "healthy" if content_count > 0 else "empty"
    
    # Get recent query metrics
    since = timezone.now() - timedelta(hours=24)
    try:
        recent_qs = SearchQuery.objects.filter(created_at__gte=since)
        recent_queries_24h = await recent_qs.acount()
        
        if recent_queries_24h > 0:
            agg = await recent_qs.aaggregate(avg_time=Avg('execution_time_ms'))
            avg_execution_time_ms = agg['avg_time'] or 0
        else:
            avg_execution_time_ms = 0
    except Exception:
        recent_queries_24h = 0
        avg_execution_time_ms = 0
    
    # Overall status
    overall_status = "healthy" if database_status == "healthy" and cache_status == "healthy" else "degraded"
    
    return HealthCheckResponse(
        status=overall_status,
        index_status=index_status,
        cache_status=cache_status,
        database_status=database_status,
        content_count=content_count,
        recent_queries_24h=recent_queries_24h,
        avg_execution_time_ms=avg_execution_time_ms,
    )


