from rest_framework import serializers
from apps.users.models import User, RestaurantProfile, CashierProfile
from apps.users.services.auth_service import AuthService
from apps.users.helpers.constants import UserRole


class RestaurantProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantProfile
        fields = (
            'id', 'restaurant_name', 'address', 'description',
            'logo_url', 'is_active', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class CashierProfileSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)

    class Meta:
        model = CashierProfile
        fields = ('id', 'restaurant', 'restaurant_name', 'is_active', 'can_set_vip', 'created_at')
        read_only_fields = ('id', 'restaurant', 'restaurant_name', 'is_active', 'can_set_vip', 'created_at')


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)
    # Optional — only relevant when role=restaurant
    restaurant_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    
    ROLE_REQUIRED_FIELDS = {
        UserRole.RESTAURANT: ['restaurant_name'],
       
    }

    class Meta:
        model = User
        fields = (
            'username', 'email', 'password', 'confirm_password',
            'role', 'phone_number', 'restaurant_name',
        )
        extra_kwargs = {
            'role': {'required': True},
            'phone_number': {'required': False},
        }

    def validate_username(self, value):
        if '@' in value:
            raise serializers.ValidationError("Username cannot contain the '@' symbol.")
        return value

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        data.pop('confirm_password')
        
        role = data.get('role')
        required_fields = self.ROLE_REQUIRED_FIELDS.get(role, [])
        for field in required_fields:
            if not data.get(field):
                raise serializers.ValidationError(
                    {field: f"{field} is required for role '{role}'."}
                )

        return data

    def create(self, validated_data):
        result = AuthService.register_user(validated_data)
        return result['user']


class LoginSerializer(serializers.Serializer):
    username_or_email = serializers.CharField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})


class UserSerializer(serializers.ModelSerializer):
    restaurant_profile = RestaurantProfileSerializer(read_only=True)
    cashier_profile = CashierProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'role', 'phone_number',
            'restaurant_profile', 'cashier_profile', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'role')


class CashierUserSerializer(serializers.ModelSerializer):
    cashier_profile = CashierProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'role', 'phone_number', 'cashier_profile', 'created_at')
        read_only_fields = fields


class CashierCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    can_set_vip = serializers.BooleanField(required=False, default=False)


class CashierUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
    can_set_vip = serializers.BooleanField(required=False)


class SetVipPermissionSerializer(serializers.Serializer):
    can_set_vip = serializers.BooleanField()


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'email', 'phone_number')
        # role is intentionally excluded – only admin can change it via a separate endpoint if needed