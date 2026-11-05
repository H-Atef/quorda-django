from rest_framework.permissions import BasePermission

from apps.users.helpers.constants import UserRole
from apps.users.helpers.restaurant import get_user_restaurant


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == UserRole.ADMIN


class IsRestaurant(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == UserRole.RESTAURANT


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == UserRole.CUSTOMER


class IsAdminOrRestaurant(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in (UserRole.ADMIN, UserRole.RESTAURANT)


class IsRestaurantOwnerOnly(BasePermission):
    message = 'Only the restaurant owner may perform this action.'

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == UserRole.RESTAURANT


class IsRestaurantStaff(BasePermission):
    message = 'Only active restaurant staff may access this resource.'

    def has_permission(self, request, view):
        return bool(get_user_restaurant(request.user))

    def has_object_permission(self, request, view, obj):
        restaurant = get_user_restaurant(request.user)
        if not restaurant:
            return False
        obj_restaurant_id = getattr(obj, 'restaurant_id', None)
        if obj_restaurant_id is None and hasattr(obj, 'order'):
            obj_restaurant_id = obj.order.restaurant_id
        return obj_restaurant_id == restaurant.id
