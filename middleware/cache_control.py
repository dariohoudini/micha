"""
HTTP Caching Middleware
Fixes: mobile apps re-download unchanged product data on every swipe.

Adds ETag and Cache-Control headers to product detail responses.
ETag is based on product.updated_at — changes when product is edited.
Mobile app sends If-None-Match header, gets 304 Not Modified if unchanged.
Saves bandwidth, reduces server load, makes app feel faster.

Usage — apply to a view:
    from middleware.cache_control import etag_response, cache_public

    @cache_public(max_age=300)  # Cache for 5 minutes in CDN
    def product_list(request): ...

    @etag_response  # Client-side ETag caching
    def product_detail(request, pk): ...
"""
import hashlib
from functools import wraps
from django.utils.http import http_date
from django.utils import timezone


def etag_response(view_func):
    """
    Decorator: Adds ETag header to response.
    Client sends If-None-Match on next request.
    Returns 304 Not Modified if content unchanged.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)

        if response.status_code == 200 and hasattr(response, 'data'):
            # Generate ETag from response content
            content = str(response.data).encode('utf-8')
            etag = f'"{hashlib.md5(content).hexdigest()}"'

            # Check if client already has this version
            if_none_match = request.META.get('HTTP_IF_NONE_MATCH', '')
            if if_none_match and if_none_match == etag:
                from rest_framework.response import Response
                return Response(status=304)

            response['ETag'] = etag
            response['Cache-Control'] = 'private, max-age=0, must-revalidate'

        return response
    return wrapper


def cache_public(max_age=300):
    """
    Decorator: Marks response as publicly cacheable (for CDN).
    Use on product lists, categories, homepage feed — public data.
    Never use on user-specific data.
    max_age: seconds to cache in CDN (default 5 minutes)
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)
            if response.status_code == 200:
                response['Cache-Control'] = f'public, max-age={max_age}, s-maxage={max_age}'
                response['Vary'] = 'Accept-Language, Accept-Encoding'
            return response
        return wrapper
    return decorator


def no_cache(view_func):
    """
    Decorator: Explicitly disable caching.
    Use on checkout, wallet, order status — data that must always be fresh.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response['Pragma'] = 'no-cache'
        return response
    return wrapper


class ProductETagMixin:
    """
    Mixin for DRF ViewSets — adds ETag based on product.updated_at.
    Most efficient: ETag changes only when product actually changes.
    """
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        # Generate ETag from last update time
        if hasattr(instance, 'updated_at'):
            etag = f'"{instance.pk}-{instance.updated_at.timestamp()}"'
            if_none_match = request.META.get('HTTP_IF_NONE_MATCH', '')
            if if_none_match == etag:
                from rest_framework.response import Response
                return Response(status=304)

        response = super().retrieve(request, *args, **kwargs)

        if hasattr(instance, 'updated_at'):
            etag = f'"{instance.pk}-{instance.updated_at.timestamp()}"'
            response['ETag'] = etag
            response['Last-Modified'] = http_date(instance.updated_at.timestamp())
            response['Cache-Control'] = 'private, max-age=0, must-revalidate'

        return response
