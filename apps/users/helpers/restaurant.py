from apps.users.helpers.constants import UserRole


def get_user_restaurant(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    role = getattr(user, 'role', None)
    if role == UserRole.RESTAURANT:
        return getattr(user, 'restaurant_profile', None)
    if role == UserRole.CASHIER:
        profile = getattr(user, 'cashier_profile', None)
        if profile and profile.is_active:
            restaurant = getattr(profile, 'restaurant', None)
            if restaurant and restaurant.is_active:
                return restaurant
    return None