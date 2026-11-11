from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.users.helpers.restaurant import get_user_restaurant
from apps.users.permissions import IsRestaurant
from apps.users.serializers import (
    CashierCreateSerializer,
    CashierUpdateSerializer,
    CashierUserSerializer,
    SetVipPermissionSerializer,
)
from apps.users.services.cashier_service import CashierService


class CashierListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    @extend_schema(tags=['cashiers'], responses=CashierUserSerializer(many=True))
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        cashiers = CashierService.list_for_restaurant(restaurant)
        return Response(CashierUserSerializer([c.user for c in cashiers], many=True).data)

    @extend_schema(tags=['cashiers'], request=CashierCreateSerializer, responses={201: CashierUserSerializer})
    def post(self, request):
        restaurant = get_user_restaurant(request.user)
        serializer = CashierCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = CashierService.create_cashier(restaurant, serializer.validated_data)
        return Response(CashierUserSerializer(profile.user).data, status=status.HTTP_201_CREATED)


class CashierDetailView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    @extend_schema(tags=['cashiers'], responses=CashierUserSerializer)
    def get(self, request, pk):
        restaurant = get_user_restaurant(request.user)
        profile = CashierService.get_owned_cashier(restaurant, pk)
        return Response(CashierUserSerializer(profile.user).data)

    @extend_schema(tags=['cashiers'], request=CashierUpdateSerializer, responses=CashierUserSerializer)
    def patch(self, request, pk):
        restaurant = get_user_restaurant(request.user)
        profile = CashierService.get_owned_cashier(restaurant, pk)
        serializer = CashierUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = CashierService.update_cashier(profile, serializer.validated_data)
        return Response(CashierUserSerializer(profile.user).data)


class CashierSetVipPermissionView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]
    serializer_class = SetVipPermissionSerializer

    @extend_schema(tags=['cashiers'], request=SetVipPermissionSerializer)
    def post(self, request):
        restaurant = get_user_restaurant(request.user)
        serializer = SetVipPermissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        count = CashierService.set_vip_permission_for_all(restaurant, serializer.validated_data['can_set_vip'])
        return Response({'updated': count, 'can_set_vip': serializer.validated_data['can_set_vip']})