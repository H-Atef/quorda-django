from rest_framework.exceptions import NotFound

from apps.users.models import User
from apps.users.helpers.validators import validate_user_update


class UserService:

    @staticmethod
    def list_users():
        """Return all users (admin only)."""
        return User.objects.all().order_by('username')

    @staticmethod
    def get_user_by_id(user_id):
        """Retrieve a single user by UUID. Raise NotFound if missing."""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise NotFound(f"User with id {user_id} not found.")

    @staticmethod
    def update_user(user, data, partial=False, requesting_user=None):
        """
        Update a user instance.
        - user: the User instance to update
        - data: dict of fields to update
        - partial: if True, do partial update (PATCH)
        - requesting_user: the user making the request (for permission checks)
        """
        validated_data = validate_user_update(user.id, data, requesting_user)

        for attr, value in validated_data.items():
            setattr(user, attr, value)
        user.save()
        return user

    @staticmethod
    def delete_user(user):
        """Delete a user instance."""
        user.delete()
