from rest_framework import permissions

class IsSellerOrSuperuser(permissions.BasePermission):
    """
    Allow access if the user is a seller OR a superuser.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (getattr(user, "is_seller", False) or user.is_superuser))

class IsVerifiedSeller(permissions.BasePermission):
    """
    Allow access only to verified sellers.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, "is_verified_seller", False))

class IsNotSuspended(permissions.BasePermission):
    """
    Deny access if the user is suspended.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not getattr(user, 'is_suspended', False))