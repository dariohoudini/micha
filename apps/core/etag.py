"""
apps/core/etag.py

Tiny ETag helper. Any read endpoint can opt in:

    from apps.core.etag import etag_for, conditional_get
    @conditional_get(lambda req, *a, **kw:
                      etag_for('seller_profile', seller_id=kw['seller_id']))
    def get(self, request, seller_id):
        ...

Or inline:

    etag = etag_for('product', pk=product.pk, updated_at=product.updated_at)
    if request.META.get('HTTP_IF_NONE_MATCH') == etag:
        return HttpResponse(status=304)
    resp = Response(data)
    resp['ETag'] = etag
    return resp

Why standardise:
  • Mobile clients on flaky cellular save bytes by sending If-None-Match
  • Server saves serializer + DB work on 304s
  • Today only ProductDetailView has ETag; this brings the pattern to
    every read endpoint with one line each.
"""
from __future__ import annotations
import hashlib
import functools

from django.http import HttpResponse
from rest_framework.response import Response


def etag_for(prefix: str, **parts) -> str:
    """Build a stable ETag from named parts. Quoted to match RFC 7232.

    parts dict is sorted by key so call-order doesn't change the hash.
    """
    blob = prefix + ':' + ':'.join(f'{k}={v!r}' for k, v in sorted(parts.items()))
    h = hashlib.sha1(blob.encode('utf-8')).hexdigest()[:24]
    return f'W/"{prefix}-{h}"'


def conditional_get(etag_fn):
    """Decorator for APIView.get methods.

    ``etag_fn`` is a callable taking (request, *args, **kwargs) → str (the
    ETag). Returns early with 304 when If-None-Match matches; otherwise
    runs the view and sets the ETag header on the response.

    The view stays in charge of side-effects (we don't short-circuit
    write-path actions; this decorator is only for GET / HEAD).
    """
    def deco(view_method):
        @functools.wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            try:
                etag = etag_fn(request, *args, **kwargs)
            except Exception:
                etag = ''
            if etag and request.META.get('HTTP_IF_NONE_MATCH') == etag:
                resp = HttpResponse(status=304)
                resp['ETag'] = etag
                return resp
            response = view_method(self, request, *args, **kwargs)
            if etag:
                try:
                    response['ETag'] = etag
                except Exception:
                    pass
            return response
        return wrapper
    return deco
