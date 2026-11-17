import re
from typing import Any, Dict, Optional, Set

from django.db import transaction, IntegrityError
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User, RestaurantProfile
from apps.users.helpers.validators import validate_registration_data
from apps.users.helpers.constants import UserRole


class AuthService:
    """
    Service layer for authentication:
    - register with role-based profile (dynamic field extraction)
    - login via username or email
    - logout via token blacklisting
    """

    # ------------------------------------------------------------------
    # Role‑specific configuration
    # ------------------------------------------------------------------

    # Each role declares which fields belong to its profile.
    PROFILE_FIELDS = {
        UserRole.RESTAURANT: {
            'restaurant_name',
            'address',
            'description',
            'logo_url',
        },
        # Future roles:
        # UserRole.CUSTOMER: {'phone', 'birth_date'},
        # UserRole.DELIVERY: {'vehicle_plate', 'license_number'},
    }

    # Union of all profile fields across all roles (so we pop them all)
    ALL_PROFILE_FIELDS = set().union(*PROFILE_FIELDS.values())

    # Precompiled email regex (avoids recompiling on every login).
    EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

    @classmethod
    def get_profile_fields_for_role(cls, role: str) -> Set[str]:
        """Return the set of profile fields for a given role, or an empty set."""
        return cls.PROFILE_FIELDS.get(role, set())

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @staticmethod
    def register_user(validated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new user and its role-specific profile.

        Any field that belongs to any profile is automatically popped from
        validated_data so it never reaches User(**validated_data).

        Password is hashed *before* opening the transaction so the DB lock
        window only covers the two INSERTs, not the CPU-bound hashing.

        Args:
            validated_data: cleaned data from the registration serializer.
                Must include at least: username, password, role.

        Returns:
            Dict with 'user' and success message.

        Raises:
            ValidationError: if the username/email is taken or profile creation fails.
        """
        # Apply custom validations (e.g., username without '@', no admin role).
        validated_data = validate_registration_data(validated_data)

        role = validated_data.get('role')
        if not role:
            raise ValidationError({"role": ["Role is required."]})

        # --- Extract ALL known profile fields (regardless of role) ---
        # This prevents any profile field from being passed to User(**validated_data).
        profile_data = {}
        for field in AuthService.ALL_PROFILE_FIELDS:
            profile_data[field] = validated_data.pop(field, None)

        # --- Hash password BEFORE opening the transaction (CPU-bound work) ---
        password = validated_data.pop('password')
        hashed_password = make_password(password)

        # --- Create the User and its profile inside a short transaction ---
        user = User(**validated_data)   # only user model fields remain
        user.password = hashed_password
        try:
            with transaction.atomic():
                user.save()
                AuthService._create_role_profile(user, profile_data)
        except IntegrityError as exc:
            raise ValidationError(
                {"username": ["This username or email is already taken."]}
            ) from exc

        return {
            'user': user,
            'message': 'User successfully registered.'
        }

    # ------------------------------------------------------------------
    # Profile creation (dispatch + creators)
    # ------------------------------------------------------------------

    @staticmethod
    def _create_role_profile(user: User, profile_data: Dict[str, Any]) -> Optional[Any]:
        """
        Dispatch to the appropriate profile creator based on the user's role.

        Uses a dictionary lookup – no conditional branching for roles.
        """
        creators = {
            UserRole.RESTAURANT: AuthService._create_restaurant_profile,
            # Add other roles here when needed
        }

        creator = creators.get(user.role)
        if creator is not None:
            return creator(user, profile_data)
        return None

    @staticmethod
    def _create_restaurant_profile(user: User, profile_data: Dict[str, Any]) -> RestaurantProfile:
        """
        Create a RestaurantProfile.

        Only the fields that RestaurantProfile accepts are used.
        The profile_data dict may contain extra fields (from other roles) – they are ignored.
        """
        # Filter to only the fields that RestaurantProfile actually has
        allowed_fields = {'restaurant_name', 'address', 'description', 'logo_url'}
        filtered_data = {k: v for k, v in profile_data.items() if k in allowed_fields}

        # Ensure restaurant_name is present (you can raise if missing, or leave None)
        # If you want to require it, uncomment:
        # if not filtered_data.get('restaurant_name'):
        #     raise ValidationError({"restaurant_name": ["This field is required."]})

        try:
            return RestaurantProfile.objects.create(user=user, **filtered_data)
        except IntegrityError as exc:
            raise ValidationError(
                {"restaurant_name": ["A restaurant profile with this name already exists."]}
            ) from exc

    # ------------------------------------------------------------------
    # Authentication (Login)
    # ------------------------------------------------------------------

    @staticmethod
    def authenticate_user(username_or_email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate by username or email.

        Single database lookup regardless of whether the identifier is an
        email or a username, then a single password hash check.

        Returns dict with user, refresh token, and access token.
        """
        user_obj = User.objects.filter(
            Q(username=username_or_email) | Q(email=username_or_email)
        ).first()

        if user_obj is None:
            raise AuthenticationFailed('Invalid credentials.')

        user = authenticate(username=user_obj.username, password=password)
        if user is None:
            raise AuthenticationFailed('Invalid credentials.')

        refresh = RefreshToken.for_user(user)
        return {
            'user': user,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    @staticmethod
    def logout_user(refresh_token: str) -> Dict[str, str]:
        """Blacklist the refresh token atomically."""
        if not refresh_token:
            raise AuthenticationFailed('No refresh token provided.')

        try:
            outstanding = OutstandingToken.objects.get(token=refresh_token)
        except OutstandingToken.DoesNotExist:
            raise AuthenticationFailed('Refresh token does not exist or is already invalid.')

        # Atomic blacklist: concurrent logouts of the same token won't duplicate.
        BlacklistedToken.objects.get_or_create(token=outstanding)
        return {"message": "Successfully logged out."}
