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
            etag = f'"{hashlib.sha256(content).hexdigest()}"'

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


class PrivateByDefaultCacheMiddleware:
    """Secure-by-default cache headers (Caching & CDN doc CH14; Security doc
    cache-bypass-of-RLS risk).

    RLS / app-layer ownership protect the DATABASE, never a shared cache.
    A per-user response that goes out WITHOUT a Cache-Control header relies
    on "the CDN probably won't cache it" — exactly the accidental-leak this
    doc warns against (one user's cart/wallet/orders served to another from
    a shared edge). This backstop guarantees the safe default: any
    AUTHENTICATED response that didn't deliberately set a cache policy is
    marked ``private, no-store`` so no shared cache (CDN/proxy) can ever
    store it. A view that genuinely wants per-user browser or CDN caching
    opts IN explicitly (e.g. @cache_public, or its own Cache-Control header)
    and is left untouched.

    Anonymous responses are NOT forced (no per-user data to leak; public
    cacheability is decided by the view / CDN rules). Defence in depth — it
    complements, never replaces, the @no_cache decorator on sensitive views.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # The view already declared a cache policy → respect it (it may be
        # a deliberate public/cacheable or no-store decision).
        if response.has_header('Cache-Control'):
            return response

        # "Private" = any credentialed request. Token-authenticated API
        # requests carry an Authorization header but may show AnonymousUser
        # at the Django layer (DRF authenticates later), so check BOTH the
        # resolved principal AND the presence of a credential header.
        user = getattr(request, 'user', None)
        is_private = (
            (user is not None and getattr(user, 'is_authenticated', False))
            or bool(request.META.get('HTTP_AUTHORIZATION'))
        )
        if is_private:
            # Per-user response with no explicit policy → never let a shared
            # cache keep it. no-store also covers the browser for safety;
            # views wanting per-user browser caching set their own header.
            response['Cache-Control'] = 'private, no-store'
            # Belt-and-braces: a shared cache that ignores Cache-Control but
            # honours Vary must still not collapse two principals' responses.
            existing_vary = response.get('Vary', '')
            if 'Cookie' not in existing_vary and 'Authorization' not in existing_vary:
                response['Vary'] = (
                    f'{existing_vary}, Cookie, Authorization' if existing_vary
                    else 'Cookie, Authorization')

        return response
