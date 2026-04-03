from rest_framework.permissions import BasePermission


class IsStoreOwner(BasePermission):
    message = "You do not own this store."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, 'store')
        )
