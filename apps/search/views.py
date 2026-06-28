# apps/search/views.py
"""
Legacy wrapper for compatibility with sync imports.
All active code has been migrated to apis/sync/ and apis/async_/.
"""

from .apis.sync.search_views import search_content, search_suggestions, search_analytics  # noqa: F401
