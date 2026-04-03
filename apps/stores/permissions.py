from rest_framework.permissions import BasePermission


class IsVerifiedSeller(BasePermission):
    message = "You must be a verified seller to perform this action."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.is_seller
            and request.user.is_verified_seller
        )
