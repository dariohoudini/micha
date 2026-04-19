"""
Standard Pagination — consistent response format across ALL list endpoints.
Every list endpoint returns:
{
    "count": 100,
    "total_pages": 5,
    "page": 1,
    "page_size": 20,
    "next": "http://api/products/?page=2",
    "previous": null,
    "results": [...]
}

Cursor pagination for real-time feeds (notifications, chat, activity):
{
    "next_cursor": "abc123",
    "previous_cursor": null,
    "results": [...]
}
"""
from rest_framework.pagination import PageNumberPagination, CursorPagination
from rest_framework.response import Response
import math


class StandardPagination(PageNumberPagination):
    """
    Standard page-based pagination for product lists, order history etc.
    Consistent format prevents frontend having to handle multiple response shapes.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'total_pages': math.ceil(self.page.paginator.count / self.get_page_size(self.request)),
            'page': self.page.number,
            'page_size': self.get_page_size(self.request),
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'count': {'type': 'integer'},
                'total_pages': {'type': 'integer'},
                'page': {'type': 'integer'},
                'page_size': {'type': 'integer'},
                'next': {'type': 'string', 'nullable': True},
                'previous': {'type': 'string', 'nullable': True},
                'results': schema,
            }
        }


class FeedCursorPagination(CursorPagination):
    """
    Cursor-based pagination for real-time feeds.
    Use this for: notifications, chat messages, activity log, personalised feed.

    Why cursor not page:
    - Page 2 breaks when new items are added between page 1 and page 2 requests
    - Cursor always points to exact position — no duplicates, no skips
    - Works correctly with real-time data insertion
    """
    page_size = 20
    ordering = '-created_at'
    cursor_query_param = 'cursor'

    def get_paginated_response(self, data):
        return Response({
            'next_cursor': self.get_next_link(),
            'previous_cursor': self.get_previous_link(),
            'page_size': self.page_size,
            'results': data,
        })


class LargeResultsPagination(StandardPagination):
    """For admin endpoints that need more results per page."""
    page_size = 50
    max_page_size = 500


class SmallResultsPagination(StandardPagination):
    """For sidebar/widget endpoints — fewer results needed."""
    page_size = 10
    max_page_size = 20
