from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema

from apps.orders.permissions import IsRestaurantOwner, IsOrderItemOwner
from apps.orders.serializers import OrderItemReadSerializer, OrderItemWriteSerializer
from apps.orders.services.order_service import OrderService
from apps.orders.services.order_item_service import OrderItemService
from apps.users.helpers.restaurant import get_user_restaurant


@extend_schema(tags=['Order Items'])
class OrderItemListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(summary='List items of an order', responses=OrderItemReadSerializer(many=True))
    def get(self, request, order_pk):
        restaurant = get_user_restaurant(request.user)
        order = OrderService.get_owned_order(restaurant, order_pk)
        items = order.order_items.select_related('menu_item__category').all()
        return Response(OrderItemReadSerializer(items, many=True).data)

    @extend_schema(summary='Add an item to an order', request=OrderItemWriteSerializer, responses={201: OrderItemReadSerializer})
    def post(self, request, order_pk):
        restaurant = get_user_restaurant(request.user)
        order = OrderService.get_owned_order(restaurant, order_pk)
        serializer = OrderItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = OrderItemService.add_item(order, serializer.validated_data)
        return Response(OrderItemReadSerializer(item).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Order Items'])
class OrderItemDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner, IsOrderItemOwner]

    @extend_schema(summary='Retrieve an order item', responses=OrderItemReadSerializer)
    def get(self, request, order_pk, pk):
        restaurant = get_user_restaurant(request.user)
        _, item = OrderService.get_owned_item(restaurant, order_pk, pk)
        return Response(OrderItemReadSerializer(item).data)

    @extend_schema(summary='Replace an order item', request=OrderItemWriteSerializer, responses=OrderItemReadSerializer)
    def put(self, request, order_pk, pk):
        restaurant = get_user_restaurant(request.user)
        _, item = OrderService.get_owned_item(restaurant, order_pk, pk)
        serializer = OrderItemWriteSerializer(item, data=request.data)
        serializer.is_valid(raise_exception=True)
        item = OrderItemService.update_item(item, serializer.validated_data, actor=request.user)
        return Response(OrderItemReadSerializer(item).data)

    @extend_schema(summary='Partially update an order item', request=OrderItemWriteSerializer, responses=OrderItemReadSerializer)
    def patch(self, request, order_pk, pk):
        restaurant = get_user_restaurant(request.user)
        _, item = OrderService.get_owned_item(restaurant, order_pk, pk)
        serializer = OrderItemWriteSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = OrderItemService.update_item(item, serializer.validated_data, actor=request.user)
        return Response(OrderItemReadSerializer(item).data)

    @extend_schema(summary='Delete an order item', responses={204: None})
    def delete(self, request, order_pk, pk):
        restaurant = get_user_restaurant(request.user)
        _, item = OrderService.get_owned_item(restaurant, order_pk, pk)
        OrderItemService.delete_item(item, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)