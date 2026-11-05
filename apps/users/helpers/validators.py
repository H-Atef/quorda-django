
from rest_framework.exceptions import ValidationError
from apps.users.helpers.constants import UserRole
from apps.users.models import User


def validate_registration_data(data):
    """
    Validate data before user creation.
    Raises ValidationError if any rule is violated.
    """
    role = data.get('role')

    # Rule: Regular registration cannot create admin or cashier users.
    if role in (UserRole.ADMIN, UserRole.CASHIER):
        raise ValidationError({
            'role': 'This role cannot be created through registration.'
        })

    return data


def validate_user_update(user_id, data, requesting_user):
    """
    Validate user update data.
    - Prevent role changes unless the requester is admin.
    - Ensure email/username uniqueness.
    """
    if 'role' in data and requesting_user.role != UserRole.ADMIN:
        raise ValidationError({'role': 'Only admin can change user role.'})

    if 'email' in data:
        exists = User.objects.exclude(pk=user_id).filter(email=data['email']).exists()
        if exists:
            raise ValidationError({'email': 'A user with this email already exists.'})

    if 'username' in data:
        exists = User.objects.exclude(pk=user_id).filter(username=data['username']).exists()
        if exists:
            raise ValidationError({'username': 'A user with this username already exists.'})

    return data