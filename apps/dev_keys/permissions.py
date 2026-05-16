"""
apps/dev_keys/permissions.py

Scope-checking permission class and decorator.

Pattern 1: class-level (whole view requires a scope)
    class OrdersListView(APIView):
        authentication_classes = [APIKeyAuthentication, SessionAuthentication]
        permission_classes = [RequiresScope('orders:read')]
        ...

Pattern 2: method-level (per-method varies)
    class OrdersView(APIView):
        @method_requires_scope('orders:read')
        def get(self, request): ...
        @method_requires_scope('orders:write')
        def post(self, request): ...

Both patterns are no-ops for non-API-key auth (a regular JWT-authenticated
user is implicitly trusted with whatever their account-level permissions
allow — scopes only constrain delegated access).
"""
from __future__ import annotations
import functools

from rest_framework import permissions
from rest_framework.response import Response


def _api_key(request):
    return getattr(request, '_api_key', None)


class RequiresScope(permissions.BasePermission):
    """Class-form permission. Constructed with the required scope string."""
    required_scope = None

    def __init__(self, *args, **kwargs):
        # DRF instantiates permission classes with no args (it calls the
        # class). We support both: PermissionClass = RequiresScope('xxx')
        # produces a *callable* that returns a class instance.
        pass

    def has_permission(self, request, view):
        # Non-API-key requests pass through — their user-level permissions
        # are checked by other classes (IsAdmin, IsAuthenticated, etc.).
        key = _api_key(request)
        if key is None:
            return True
        return key.has_scope(self.required_scope)


def make_scope_permission(scope: str):
    """Factory returning a DRF permission class for ``scope``."""
    return type(
        f'RequiresScope_{scope.replace(":", "_")}',
        (RequiresScope,),
        {'required_scope': scope},
    )


def method_requires_scope(scope: str):
    """Decorator for individual APIView methods. Refuses API-key requests
    that lack the scope; pass-through for non-API-key auth."""
    def decorator(view_method):
        @functools.wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            key = _api_key(request)
            if key is not None and not key.has_scope(scope):
                return Response(
                    {'error': 'insufficient_scope',
                     'detail': f'This endpoint requires scope: {scope}',
                     'required_scope': scope},
                    status=403,
                )
            return view_method(self, request, *args, **kwargs)
        return wrapper
    return decorator
