from rest_framework.permissions import BasePermission

from apps.users.helpers.restaurant import get_user_restaurant


class IsRestaurantOwner(BasePermission):
    """Restaurant owner or active cashier for the scoped restaurant."""

    def has_permission(self, request, view):
        return bool(get_user_restaurant(request.user))

    def has_object_permission(self, request, view, obj):
        restaurant = get_user_restaurant(request.user)
        return bool(restaurant and obj.restaurant_id == restaurant.id)


class IsOrderItemOwner(BasePermission):
    """Staff may only act on items belonging to their own restaurant orders."""

    def has_object_permission(self, request, view, obj):
        restaurant = get_user_restaurant(request.user)
        return bool(restaurant and obj.order.restaurant_id == restaurant.id)


class IsOrderCustomer(BasePermission):
    """Authenticated users may only view/modify/cancel their own delivery
    orders (is_indoor=False, customer=request.user)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return obj.is_indoor is False and obj.customer_id == request.user.id
