# apps/search/metrics.py
"""
Search metrics export for monitoring systems (Prometheus, Datadog, etc.).
Tracks search performance, cache hit rates, and query patterns。
"""

import time
from typing import Dict, Any, Optional
from django.core.cache import cache
from django.conf import settings
from django.db.models import Count, Avg
from django.utils import timezone
from datetime import timedelta

from .models import SearchQuery, SearchableContent


class SearchMetrics:
    """Search metrics collector and exporter."""

    def __init__(self):
        self.metrics_prefix = 'search_'
        self.cache_ttl = getattr(settings, 'SEARCH_METRICS_CACHE_TTL', 60)

    def get_performance_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get search performance metrics for the specified time period.
        Returns execution times, query counts, and cache statistics.
        """
        since = timezone.now() - timedelta(hours=hours)
        queryset = SearchQuery.objects.filter(created_at__gte=since)

        total_queries = queryset.count()
        if total_queries == 0:
            return {
                'total_queries': 0,
                'avg_execution_time_ms': 0,
                'p50_execution_time_ms': 0,
                'p95_execution_time_ms': 0,
                'p99_execution_time_ms': 0,
                'zero_result_rate': 0.0,
            }

        # Average execution time
        avg_result = queryset.aggregate(avg_time=Avg('execution_time_ms'))
        avg_execution_time = avg_result['avg_time'] or 0

        # Percentiles (simplified - in production use proper percentile calculation)
        execution_times = list(queryset.values_list('execution_time_ms', flat=True).order_by('execution_time_ms'))
        execution_times.sort()
        
        p50 = execution_times[len(execution_times) // 2] if execution_times else 0
        p95 = execution_times[int(len(execution_times) * 0.95)] if execution_times else 0
        p99 = execution_times[int(len(execution_times) * 0.99)] if execution_times else 0

        # Zero result rate
        zero_result_count = queryset.filter(results_count=0).count()
        zero_result_rate = zero_result_count / total_queries if total_queries > 0 else 0.0

        return {
            'total_queries': total_queries,
            'avg_execution_time_ms': avg_execution_time,
            'p50_execution_time_ms': p50,
            'p95_execution_time_ms': p95,
            'p99_execution_time_ms': p99,
            'zero_result_rate': zero_result_rate,
        }

    def get_cache_metrics(self) -> Dict[str, Any]:
        """
        Get cache performance metrics.
        Returns cache hit rate and cache size statistics.
        """
        # Cache hit rate (estimated from recent queries)
        cache_hits_key = f"{self.metrics_prefix}cache_hits"
        cache_misses_key = f"{self.metrics_prefix}cache_misses"
        
        hits = cache.get(cache_hits_key, 0)
        misses = cache.get(cache_misses_key, 0)
        total = hits + misses
        
        cache_hit_rate = hits / total if total > 0 else 0.0

        return {
            'cache_hits': hits,
            'cache_misses': misses,
            'cache_hit_rate': cache_hit_rate,
            'total_cache_operations': total,
        }

    def get_index_metrics(self) -> Dict[str, Any]:
        """
        Get search index metrics.
        Returns content counts by type and index freshness.
        """
        content_counts = SearchableContent.objects.values('content_type').annotate(
            count=Count('id')
        ).order_by('content_type')

        content_by_type = {item['content_type']: item['count'] for item in content_counts}
        total_content = sum(content_by_type.values())

        # Index freshness (time since last indexed content)
        latest_content = SearchableContent.objects.order_by('-created_at').first()
        if latest_content:
            hours_since_index = (timezone.now() - latest_content.created_at).total_seconds() / 3600
        else:
            hours_since_index = 0

        return {
            'total_indexed_content': total_content,
            'content_by_type': content_by_type,
            'hours_since_last_index': hours_since_index,
        }

    def get_query_patterns(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get query pattern metrics.
        Returns top queries, average query length, and filter usage.
        """
        since = timezone.now() - timedelta(hours=hours)
        queryset = SearchQuery.objects.filter(created_at__gte=since)

        # Average query length
        queries = queryset.values_list('query_text', flat=True)
        avg_query_length = sum(len(q) for q in queries) / len(queries) if queries else 0

        # Filter usage
        queries_with_filters = queryset.exclude(filters={}).count()
        total_queries = queryset.count()
        filter_usage_rate = queries_with_filters / total_queries if total_queries > 0 else 0.0

        return {
            'avg_query_length': avg_query_length,
            'filter_usage_rate': filter_usage_rate,
            'queries_with_filters': queries_with_filters,
        }

    def record_cache_hit(self):
        """Record a cache hit event."""
        cache_hits_key = f"{self.metrics_prefix}cache_hits"
        current = cache.get(cache_hits_key, 0)
        cache.set(cache_hits_key, current + 1, self.cache_ttl)

    def record_cache_miss(self):
        """Record a cache miss event."""
        cache_misses_key = f"{self.metrics_prefix}cache_misses"
        current = cache.get(cache_misses_key, 0)
        cache.set(cache_misses_key, current + 1, self.cache_ttl)

    def get_all_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get all search metrics in a single call.
        Useful for dashboard and monitoring systems.
        """
        return {
            'performance': self.get_performance_metrics(hours),
            'cache': self.get_cache_metrics(),
            'index': self.get_index_metrics(),
            'query_patterns': self.get_query_patterns(hours),
            'timestamp': timezone.now().isoformat(),
        }


# Singleton instance for easy import
search_metrics = SearchMetrics()
