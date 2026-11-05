from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.users.helpers.constants import UserRole
from apps.users.models import CashierProfile, User
from apps.users.services.user_service import UserService


class CashierService:
    @staticmethod
    def list_for_restaurant(restaurant):
        return CashierProfile.objects.filter(restaurant=restaurant).select_related('user', 'restaurant')

    @staticmethod
    @transaction.atomic
    def create_cashier(restaurant, validated_data):
        can_set_vip = validated_data.pop('can_set_vip', False)
        username = validated_data.pop('username')
        email = validated_data.pop('email')
        password = validated_data.pop('password')
        phone_number = validated_data.pop('phone_number', None)
        if User.objects.filter(username=username).exists():
            raise ValidationError({'username': 'A user with this username already exists.'})
        if User.objects.filter(email=email).exists():
            raise ValidationError({'email': 'A user with this email already exists.'})
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role=UserRole.CASHIER,
            phone_number=phone_number,
        )
        return CashierProfile.objects.create(
            user=user,
            restaurant=restaurant,
            can_set_vip=bool(can_set_vip),
            is_active=True,
        )

    @staticmethod
    def get_owned_cashier(restaurant, cashier_pk):
        try:
            return CashierProfile.objects.select_related('user', 'restaurant').get(pk=cashier_pk, restaurant=restaurant)
        except CashierProfile.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Cashier not found.')

    @staticmethod
    def update_cashier(profile, validated_data):
        for attr in ('is_active', 'can_set_vip'):
            if attr in validated_data:
                setattr(profile, attr, validated_data[attr])
        profile.save()
        return profile

    @staticmethod
    def set_vip_permission_for_all(restaurant, can_set_vip):
        return CashierProfile.objects.filter(restaurant=restaurant).update(can_set_vip=bool(can_set_vip))