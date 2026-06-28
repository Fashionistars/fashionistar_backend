# apps/search/apis/sync/search_views.py
"""
DRF sync views for the search domain (compatibility layer).
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.db.models import Avg

from ...services import HybridSearchService
from ...models import SearchQuery as SearchQueryModel
from apps.common.decorators import with_api_ingress


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@with_api_ingress(rate_limit=200, rate_window=60)
def search_content(request):
    """
    Perform hybrid search on all content.

    Query parameters:
    - q: search query text (required)
    - encounter_id: filter by encounter ID
    - content_type: one of (encounter, transcript, soap, checklist, notes)
    - date_from: YYYY-MM-DD
    - date_to: YYYY-MM-DD
    - page: page number
    - page_size: page size (default 20, max 100)
    """
    query_text = request.GET.get('q', '').strip()

    if not query_text:
        return Response(
            {'error': 'Query parameter "q" is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    filters = {}

    if request.GET.get('encounter_id'):
        try:
            filters['encounter_id'] = int(request.GET.get('encounter_id'))
        except ValueError:
            return Response(
                {'error': 'Invalid encounter_id format'},
                status=status.HTTP_400_BAD_REQUEST
            )

    if request.GET.get('content_type'):
        content_types = request.GET.getlist('content_type')
        valid_types = ['encounter', 'transcript', 'soap', 'checklist', 'notes']
        invalid_types = [ct for ct in content_types if ct not in valid_types]
        if invalid_types:
            return Response(
                {
                    'error': f'Invalid content types: {invalid_types}',
                    'valid_types': valid_types
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        filters['content_type'] = content_types

    if request.GET.get('date_from'):
        date_from = parse_date(request.GET.get('date_from'))
        if not date_from:
            return Response(
                {'error': 'Invalid date_from format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        filters['date_from'] = date_from

    if request.GET.get('date_to'):
        date_to = parse_date(request.GET.get('date_to'))
        if not date_to:
            return Response(
                {'error': 'Invalid date_to format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        filters['date_to'] = date_to

    page = int(request.GET.get('page', 1))
    page_size = min(int(request.GET.get('page_size', 20)), 100)

    search_service = HybridSearchService()
    search_results = search_service.search(
        query_text=query_text,
        user=request.user,
        filters=filters,
        limit=page_size * 5
    )

    paginator = Paginator(search_results['results'], page_size)
    page_obj = paginator.get_page(page)

    return Response({
        'query': query_text,
        'filters': filters,
        'results': list(page_obj),
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'total_results': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous()
        },
        'execution_time_ms': search_results['execution_time_ms'],
        'search_id': search_results['search_id']
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@with_api_ingress(rate_limit=200, rate_window=60)
def search_suggestions(request):
    """
    Provide search suggestions based on query history.

    Query parameters:
    - q: query prefix (min 2 characters)
    - limit: max suggestions (default 10)
    """
    query_prefix = request.GET.get('q', '').strip()

    if not query_prefix or len(query_prefix) < 2:
        return Response(
            {'error': 'Query prefix must be at least 2 characters'},
            status=status.HTTP_400_BAD_REQUEST
        )

    limit = min(int(request.GET.get('limit', 10)), 20)

    suggestions = SearchQueryModel.objects.filter(
        query_text__icontains=query_prefix,
        results_count__gt=0
    ).values('query_text').distinct().order_by('-id')[:limit]

    suggestion_list = [s['query_text'] for s in suggestions]

    return Response({
        'query_prefix': query_prefix,
        'suggestions': suggestion_list
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@with_api_ingress(rate_limit=200, rate_window=60)
def search_analytics(request):
    """
    Simple search analytics: count and average execution time in recent days.
    """
    try:
        days = int(request.GET.get('days', 30))
    except ValueError:
        return Response({'error': 'Invalid days parameter'}, status=status.HTTP_400_BAD_REQUEST)

    if days < 1 or days > 365:
        return Response(
            {'error': 'Days parameter must be between 1 and 365'},
            status=status.HTTP_400_BAD_REQUEST
        )

    since = timezone.now() - timezone.timedelta(days=days)
    qs = SearchQueryModel.objects.filter(created_at__gte=since)
    total = qs.count()
    
    # Corrected aggregation syntax
    avg_time = qs.aggregate(models_avg=Avg('execution_time_ms'))['models_avg'] if total else 0

    return Response({
        'since_days': days,
        'total_queries': total,
        'average_execution_time_ms': int(avg_time or 0),
    })
