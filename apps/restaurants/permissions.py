from rest_framework.permissions import BasePermission

from apps.users.helpers.constants import UserRole
from apps.users.helpers.restaurant import get_user_restaurant


class IsRestaurantOwner(BasePermission):
    """
    Allows access to authenticated restaurant owners and active cashiers with an
    active restaurant. Use IsRestaurantOwnerOnly for owner-only write actions.
    """
    message = 'Only active restaurant staff with an active profile may access this resource.'

    def has_permission(self, request, view):
        return bool(get_user_restaurant(request.user))


class IsRestaurantOwnerOnly(BasePermission):
    message = 'Only the restaurant owner may perform this action.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.RESTAURANT
            and bool(get_user_restaurant(request.user))
        )
