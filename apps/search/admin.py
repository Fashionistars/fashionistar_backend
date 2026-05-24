"""
پیکربندی ادمین برای اپ جستجو
Admin configuration for search app.
"""

from django.contrib import admin
from .models import SearchableContent, SearchQuery, SearchResult


@admin.register(SearchableContent)
class SearchableContentAdmin(admin.ModelAdmin):
    """Admin interface for SearchableContent."""

    list_display = ['id', 'title', 'content_type', 'encounter', 'content_preview', 'created_at']
    list_filter = ['content_type', 'created_at']
    search_fields = ['title', 'content']
    ordering = ['-created_at']

    fieldsets = (
        (None, {
            'fields': ('encounter', 'content_type', 'content_id', 'title')
        }),
        ('Content', {
            'fields': ('content',),
            'classes': ('collapse',)
        }),
        ('Search Data', {
            'fields': ('search_vector',),
            'classes': ('collapse',),
            'description': 'Full-text helper fields'
        }),
        ('Metadata', {
            'fields': ('metadata', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    readonly_fields = ['search_vector', 'created_at', 'updated_at']

    def content_preview(self, obj):
        """Get preview of content."""
        if obj.content:
            return obj.content[:100] + "..." if len(obj.content) > 100 else obj.content
        return "(No content)"
    content_preview.short_description = 'Content Preview'


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    """Admin interface for SearchQuery."""

    list_display = ['id', 'query_preview', 'user', 'results_count', 'execution_time_ms', 'created_at']
    list_filter = ['created_at', 'results_count']
    search_fields = ['query_text', 'user__username']
    ordering = ['-created_at']

    fieldsets = (
        (None, {
            'fields': ('query_text', 'user', 'results_count', 'execution_time_ms')
        }),
        ('Filters', {
            'fields': ('filters',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )

    readonly_fields = ['created_at']

    def query_preview(self, obj):
        """Get preview of query text."""
        return obj.query_text[:50] + "..." if len(obj.query_text) > 50 else obj.query_text
    query_preview.short_description = 'Query'


@admin.register(SearchResult)
class SearchResultAdmin(admin.ModelAdmin):
    """Admin interface for SearchResult."""

    list_display = ['id', 'query', 'content', 'relevance_score', 'rank']
    list_filter = ['relevance_score', 'rank']
    search_fields = ['query__query_text', 'content__title', 'snippet']
    ordering = ['query', 'rank']

    fieldsets = (
        (None, {
            'fields': ('query', 'content', 'relevance_score', 'rank')
        }),
        ('Content', {
            'fields': ('snippet',),
            'classes': ('collapse',)
        })
    )

