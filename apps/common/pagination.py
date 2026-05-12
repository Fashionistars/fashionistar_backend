# apps/common/pagination.py
"""
Standardized pagination for all Fashionistar API endpoints.

All paginator classes return a consistent envelope:

    {
        "success": true,
        "count":    <total items across all pages>,
        "pages":    <total number of pages>,
        "page":     <current page number>,
        "page_size":<effective page size used>,
        "next":     "<url>" | null,
        "previous": "<url>" | null,
        "results":  [ ... ]
    }

Paginator    page_size   max_page_size   Use-case
──────────────────────────────────────────────────────────────
Default          20          100         General list endpoints
Small            10           50         Mobile-first / widgets
Large            50          200         Export / admin views
Cursor           20           —          High-throughput feeds (infinite scroll)

The ?page_size=N query param (1 ≤ N ≤ max) overrides the default at runtime.
The ?cursor=<token> query param is used by CursorPagination.

Usage in DRF ViewSet::

    from apps.common.pagination import DefaultPagination

    class ProductViewSet(ModelViewSet):
        pagination_class = DefaultPagination

Usage in a function-based DRF view::

    from apps.common.pagination import paginate_queryset

    def product_list(request):
        qs = Product.objects.all()
        return paginate_queryset(request, qs, DefaultPagination)

Usage in Django Ninja (manual)::

    from apps.common.pagination import ninja_paginate

    @router.get('/products')
    def product_list(request, page: int = 1, page_size: int = 20):
        qs = Product.objects.filter(is_deleted=False)
        return ninja_paginate(request, qs, page=page, page_size=page_size)
"""

from __future__ import annotations

import math
from typing import Any

from rest_framework.pagination import (
    CursorPagination,
    PageNumberPagination,
)
from rest_framework.request import Request
from rest_framework.response import Response


# ---------------------------------------------------------------------------
# Base mixin — shared envelope structure
# ---------------------------------------------------------------------------

class _FashionistarPaginationMixin:
    """
    Mixin that overrides get_paginated_response() to return the standard
    Fashionistar envelope for every paginator class.
    """

    def get_paginated_response(self, data: list) -> Response:  # type: ignore[override]
        request: Request = self.request  # type: ignore[attr-defined]

        # For CursorPagination page/pages don't apply
        count = self.page.paginator.count if hasattr(self, "page") else None  # type: ignore[attr-defined]
        page_size = self.get_page_size(request)  # type: ignore[attr-defined]
        pages = math.ceil(count / page_size) if (count and page_size) else None
        page_number = (
            self.page.number if hasattr(self, "page") else None  # type: ignore[attr-defined]
        )

        return Response({
            "success":   True,
            "count":     count,
            "pages":     pages,
            "page":      page_number,
            "page_size": page_size,
            "next":      self.get_next_link(),  # type: ignore[attr-defined]
            "previous":  self.get_previous_link(),  # type: ignore[attr-defined]
            "results":   data,
        })

    def get_paginated_response_schema(self, schema: dict) -> dict:  # type: ignore[override]
        """drf-spectacular / OpenAPI schema for the paginated envelope."""
        return {
            "type": "object",
            "properties": {
                "success":   {"type": "boolean", "example": True},
                "count":     {"type": "integer", "nullable": True},
                "pages":     {"type": "integer", "nullable": True},
                "page":      {"type": "integer", "nullable": True},
                "page_size": {"type": "integer"},
                "next":      {"type": "string", "format": "uri", "nullable": True},
                "previous":  {"type": "string", "format": "uri", "nullable": True},
                "results":   schema,
            },
            "required": ["success", "count", "next", "previous", "results"],
        }


# ---------------------------------------------------------------------------
# Page-number paginators
# ---------------------------------------------------------------------------

class DefaultPagination(_FashionistarPaginationMixin, PageNumberPagination):
    """
    Default paginator for general list endpoints.
    page_size=20, max=100, controlled via ?page_size=N.
    """
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"


class SmallPagination(_FashionistarPaginationMixin, PageNumberPagination):
    """
    Compact paginator for widget / mobile-first endpoints.
    page_size=10, max=50.
    """
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50
    page_query_param = "page"


class LargePagination(_FashionistarPaginationMixin, PageNumberPagination):
    """
    Large paginator for export / admin list endpoints.
    page_size=50, max=200.
    """
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    page_query_param = "page"


# ---------------------------------------------------------------------------
# Cursor paginator (for feeds / infinite scroll)
# ---------------------------------------------------------------------------

class FeedCursorPagination(_FashionistarPaginationMixin, CursorPagination):
    """
    Cursor-based paginator for high-velocity, insert-heavy feeds.

    Advantages over page-number:
    - O(1) DB query regardless of page depth
    - Stable across concurrent inserts (no page drift)
    - Opaque cursor prevents enumeration attacks

    Ordered by -created_at (newest first).
    page_size=20, max=100.
    """
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-created_at"
    cursor_query_param = "cursor"

    def get_paginated_response(self, data: list) -> Response:  # type: ignore[override]
        """Cursor paginators have no count/pages — use simplified envelope."""
        request: Request = self.request  # type: ignore[attr-defined]
        page_size = self.get_page_size(request)

        return Response({
            "success":   True,
            "count":     None,      # Not knowable without full scan
            "pages":     None,      # N/A for cursor pagination
            "page":      None,      # N/A for cursor pagination
            "page_size": page_size,
            "next":      self.get_next_link(),
            "previous":  self.get_previous_link(),
            "results":   data,
        })


# ---------------------------------------------------------------------------
# Helpers for FBV / Ninja usage
# ---------------------------------------------------------------------------

def paginate_queryset(
    request: Any,
    queryset: Any,
    paginator_class: type = DefaultPagination,
) -> Response:
    """
    Paginate *queryset* and return a DRF Response.
    Designed for function-based DRF views that don't use GenericAPIView.

    Args:
        request:         DRF or Django HttpRequest.
        queryset:        QuerySet or list.
        paginator_class: Paginator class to use (default: DefaultPagination).

    Returns:
        Response: Paginated DRF response with the standard envelope.

    Example::

        def product_list(request):
            qs = Product.objects.active()
            return paginate_queryset(request, qs, SmallPagination)
    """
    paginator = paginator_class()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        return paginator.get_paginated_response(page)
    # Fallback: full list without pagination
    return Response({"success": True, "count": len(queryset), "results": list(queryset)})


def ninja_paginate(
    request: Any,
    queryset: Any,
    *,
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100,
) -> dict:
    """
    Manual pagination for Django Ninja endpoints (which bypass DRF pagination).

    Returns a plain dict (not a DRF Response) compatible with Ninja's JSON
    serialization.

    Args:
        request:       Django HttpRequest (for future URL generation).
        queryset:      QuerySet or list.
        page:          1-indexed page number.
        page_size:     Items per page (capped at max_page_size).
        max_page_size: Hard cap applied regardless of caller input.

    Returns:
        dict with standard Fashionistar pagination envelope.

    Example::

        @router.get('/products')
        def product_list(request, page: int = 1, page_size: int = 20):
            qs = Product.objects.active()
            return ninja_paginate(request, qs, page=page, page_size=page_size)
    """
    # Guard inputs
    page_size = max(1, min(int(page_size), max_page_size))
    page = max(1, int(page))

    total: int
    if hasattr(queryset, "count"):
        total = queryset.count()
    else:
        total = len(queryset)

    pages = math.ceil(total / page_size) if total else 1
    # Clamp page to valid range
    page = min(page, pages)

    offset = (page - 1) * page_size
    slice_data = queryset[offset: offset + page_size]

    # Serialize queryset slice to list of dicts if possible
    if hasattr(slice_data, "values"):
        results = list(slice_data)
    else:
        results = list(slice_data)

    return {
        "success":   True,
        "count":     total,
        "pages":     pages,
        "page":      page,
        "page_size": page_size,
        "next":      None,      # Full URL generation requires request.build_absolute_uri
        "previous":  None,      # Add if needed
        "results":   results,
    }


async def async_ninja_paginate(
    request: Any,
    queryset: Any,
    *,
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100,
) -> dict:
    """
    Async pagination for Django Ninja endpoints.

    Leverages Django 6.0's native async queryset methods (``acount()`` and
    ``__aiter__()``) to avoid blocking the event loop.

    Args:
        request:       Django HttpRequest (for future URL generation).
        queryset:      QuerySet or async iterable.
        page:          1-indexed page number.
        page_size:     Items per page (capped at max_page_size).
        max_page_size: Hard cap applied regardless of caller input.

    Returns:
        dict with standard Fashionistar pagination envelope.
    """
    page_size = max(1, min(int(page_size), max_page_size))
    page = max(1, int(page))

    total: int
    if hasattr(queryset, 'acount'):
        total = await queryset.acount()
    elif hasattr(queryset, 'count'):
        # asyncio.to_thread — correct Django 6.0 idiom, no asgiref import
        import asyncio as _asyncio
        total = await _asyncio.to_thread(queryset.count)

    else:
        total = len(queryset)

    pages = math.ceil(total / page_size) if total else 1
    page = min(page, pages)

    offset = (page - 1) * page_size
    slice_data = queryset[offset: offset + page_size]

    # Evaluate slice asynchronously
    if hasattr(slice_data, "__aiter__"):
        results = [obj async for obj in slice_data]
    else:
        results = list(slice_data)

    return {
        "success":   True,
        "count":     total,
        "pages":     pages,
        "page":      page,
        "page_size": page_size,
        "next":      None,
        "previous":  None,
        "results":   results,
    }
