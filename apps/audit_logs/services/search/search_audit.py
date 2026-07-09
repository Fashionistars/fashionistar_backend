# apps/audit_logs/services/search/search_audit.py
"""
Audit logging helpers for Search domain.
Follows vendor pattern with thin wrappers delegating to AuditService.
"""

from apps.audit_logs.services import AuditService
from apps.audit_logs.models import EventType, EventCategory


class SearchAuditService:
    """Audit service for Search domain events."""
    
    @staticmethod
    def log_search_query_executed(actor, query_id, query_text, filters, request=None):
        """Log when search query is executed."""
        AuditService.log(
            event_type=EventType.SEARCH_QUERY_EXECUTED,
            event_category=EventCategory.SEARCH,
            actor=actor,
            action="Search query executed",
            request=request,
            details={
                'query_id': str(query_id),
                'query_text': query_text[:100],  # Truncate for privacy
                'filters': filters,
            },
        )
    
    @staticmethod
    def log_search_result_returned(actor, query_id, result_count, execution_time, request=None):
        """Log when search results are returned."""
        AuditService.log(
            event_type=EventType.SEARCH_RESULT_RETURNED,
            event_category=EventCategory.SEARCH,
            actor=actor,
            action="Search results returned",
            request=request,
            details={
                'query_id': str(query_id),
                'result_count': result_count,
                'execution_time_ms': execution_time,
            },
        )
    
    @staticmethod
    def log_search_zero_results(actor, query_id, query_text, request=None):
        """Log when search returns zero results."""
        AuditService.log(
            event_type=EventType.SEARCH_ZERO_RESULTS,
            event_category=EventCategory.SEARCH,
            actor=actor,
            action="Search returned zero results",
            request=request,
            details={
                'query_id': str(query_id),
                'query_text': query_text[:100],
            },
        )
    
    @staticmethod
    def log_search_cache_hit(actor, query_id, cache_key, request=None):
        """Log when search cache is hit."""
        AuditService.log(
            event_type=EventType.SEARCH_CACHE_HIT,
            event_category=EventCategory.SEARCH,
            actor=actor,
            action="Search cache hit",
            request=request,
            details={
                'query_id': str(query_id),
                'cache_key': cache_key,
            },
        )
    
    @staticmethod
    def log_search_cache_miss(actor, query_id, cache_key, request=None):
        """Log when search cache is missed."""
        AuditService.log(
            event_type=EventType.SEARCH_CACHE_MISS,
            event_category=EventCategory.SEARCH,
            actor=actor,
            action="Search cache miss",
            request=request,
            details={
                'query_id': str(query_id),
                'cache_key': cache_key,
            },
        )
    
    @staticmethod
    def log_search_index_updated(actor, content_type, content_count, request=None):
        """Log when search index is updated."""
        AuditService.log(
            event_type=EventType.SEARCH_INDEX_UPDATED,
            event_category=EventCategory.SEARCH,
            actor=actor,
            action="Search index updated",
            request=request,
            details={
                'content_type': content_type,
                'content_count': content_count,
            },
        )
    
    @staticmethod
    def log_search_index_failed(actor, error_message, request=None):
        """Log when search index operation fails."""
        AuditService.log(
            event_type=EventType.SEARCH_INDEX_FAILED,
            event_category=EventCategory.SEARCH,
            actor=actor,
            action="Search index operation failed",
            request=request,
            details={
                'error_message': error_message,
            },
        )
