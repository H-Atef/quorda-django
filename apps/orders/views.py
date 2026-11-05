from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.orders.models import Order
from apps.orders.permissions import IsOrderCustomer, IsOrderItemOwner, IsRestaurantOwner
from apps.orders.serializers import (
    CustomerOrderCreateSerializer,
    CustomerOrderUpdateSerializer,
    OrderItemReadSerializer,
    OrderItemWriteSerializer,
    OrderSerializer,
    OrderWriteSerializer,
)
from apps.orders.services import CustomerOrderService, OrderService
from apps.users.helpers.restaurant import get_user_restaurant


WINDOW_SIZE_PARAM = OpenApiParameter(
    name='window_size',
    type=OpenApiTypes.INT,
    location=OpenApiParameter.QUERY,
    required=False,
    default=10,
    description='Number of orders per chronological window.',
)

STATUS_PARAM = OpenApiParameter(
    name='status',
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=False,
    description='Comma-separated order statuses to include (default: pending,preparing).',
)

IS_INDOOR_PARAM = OpenApiParameter(
    name='is_indoor',
    type=OpenApiTypes.BOOL,
    location=OpenApiParameter.QUERY,
    required=False,
    description='Filter by channel: true (dine-in), false (delivery), or omit for both.',
)


# ============================================================================
# Restaurant-owner/cashier endpoints
# ============================================================================


@extend_schema(tags=['Orders'])
class OrderListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(summary='List orders', responses=OrderSerializer(many=True))
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        orders = OrderService.get_restaurant_orders_qs(restaurant)
        return Response(OrderSerializer(orders, many=True).data)

    @extend_schema(summary='Create an order', request=OrderWriteSerializer, responses={201: OrderSerializer})
    def post(self, request):
        if 'is_indoor' in request.data and request.data.get('is_indoor') is False:
            raise ValidationError({'is_indoor': 'Restaurant endpoints create dine-in orders only. Use the customer delivery endpoints for delivery orders.'})
        if str(request.data.get('is_indoor', '')).lower() == 'false':
            raise ValidationError({'is_indoor': 'Restaurant endpoints create dine-in orders only. Use the customer delivery endpoints for delivery orders.'})
        serializer = OrderWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        restaurant = get_user_restaurant(request.user)
        order = OrderService.create_order(restaurant, serializer.validated_data, actor=request.user)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Orders'])
class OrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(summary='Retrieve an order', responses=OrderSerializer)
    def get(self, request, pk):
        restaurant = get_user_restaurant(request.user)
        order = OrderService.get_owned_order(restaurant, pk)
        return Response(OrderSerializer(order).data)

    @extend_schema(summary='Replace an order', request=OrderWriteSerializer, responses=OrderSerializer)
    def put(self, request, pk):
        restaurant = get_user_restaurant(request.user)
        order = OrderService.get_owned_order(restaurant, pk)
        serializer = OrderWriteSerializer(order, data=request.data)
        serializer.is_valid(raise_exception=True)
        order = OrderService.update_order(order, serializer.validated_data, actor=request.user)
        return Response(OrderSerializer(order).data)

    @extend_schema(summary='Partially update an order', request=OrderWriteSerializer, responses=OrderSerializer)
    def patch(self, request, pk):
        restaurant = get_user_restaurant(request.user)
        order = OrderService.get_owned_order(restaurant, pk)
        serializer = OrderWriteSerializer(order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        order = OrderService.update_order(order, serializer.validated_data, actor=request.user)
        return Response(OrderSerializer(order).data)

    @extend_schema(summary='Delete an order', responses={204: None})
    def delete(self, request, pk):
        restaurant = get_user_restaurant(request.user)
        order = OrderService.get_owned_order(restaurant, pk)
        OrderService.cancel_order(order, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=['Orders'])
class VIPOrdersAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(summary='List VIP orders', responses=OrderSerializer(many=True))
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        vip = OrderService.get_vip_orders(restaurant)
        return Response(OrderSerializer(vip, many=True).data)


@extend_schema(tags=['Orders'])
class WindowedOrdersAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(parameters=[WINDOW_SIZE_PARAM, STATUS_PARAM, IS_INDOOR_PARAM], responses=OrderSerializer(many=True))
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        window_size = _parse_window_size(request)
        statuses = _parse_statuses(request)
        is_indoor = _parse_is_indoor(request)
        sorted_orders = OrderService.get_windowed_orders(restaurant, window_size, statuses=statuses, is_indoor=is_indoor)
        return Response(OrderSerializer(sorted_orders, many=True).data)


@extend_schema(tags=['Orders'])
class OrdersByCreationTimeAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(responses=OrderSerializer(many=True))
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        orders = OrderService.get_restaurant_orders_qs(restaurant)
        return Response(OrderSerializer(orders, many=True).data)


@extend_schema(tags=['Orders'])
class NormalOrdersWindowedAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(parameters=[WINDOW_SIZE_PARAM, STATUS_PARAM, IS_INDOOR_PARAM], responses=OrderSerializer(many=True))
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        window_size = _parse_window_size(request)
        statuses = _parse_statuses(request)
        is_indoor = _parse_is_indoor(request)
        sorted_orders = OrderService.get_normal_windowed_orders(restaurant, window_size, statuses=statuses, is_indoor=is_indoor)
        return Response(OrderSerializer(sorted_orders, many=True).data)


@extend_schema(tags=['Orders'])
class SimpleOrdersAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(responses=OrderSerializer(many=True))
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        simple = OrderService.get_simple_orders(restaurant)
        return Response(OrderSerializer(simple, many=True).data)


# ============================================================================
# Order Items
# ============================================================================


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
        item = OrderService.add_item(order, serializer.validated_data)
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
        item = OrderService.update_item(item, serializer.validated_data, actor=request.user)
        return Response(OrderItemReadSerializer(item).data)

    @extend_schema(summary='Partially update an order item', request=OrderItemWriteSerializer, responses=OrderItemReadSerializer)
    def patch(self, request, order_pk, pk):
        restaurant = get_user_restaurant(request.user)
        _, item = OrderService.get_owned_item(restaurant, order_pk, pk)
        serializer = OrderItemWriteSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = OrderService.update_item(item, serializer.validated_data, actor=request.user)
        return Response(OrderItemReadSerializer(item).data)

    @extend_schema(summary='Delete an order item', responses={204: None})
    def delete(self, request, order_pk, pk):
        restaurant = get_user_restaurant(request.user)
        _, item = OrderService.get_owned_item(restaurant, order_pk, pk)
        OrderService.delete_item(item, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# Customer endpoints (delivery orders: is_indoor=False)
# ============================================================================


@extend_schema(tags=['Customer Orders'])
class CustomerOrderListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='List my delivery orders', responses=OrderSerializer(many=True))
    def get(self, request):
        orders = CustomerOrderService.get_customer_orders_qs(request.user)
        return Response(OrderSerializer(orders, many=True).data)

    @extend_schema(summary='Place a new delivery order', request=CustomerOrderCreateSerializer, responses={201: OrderSerializer})
    def post(self, request):
        serializer = CustomerOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        restaurant = validated_data.pop('restaurant')
        order = CustomerOrderService.create_order(request.user, restaurant, validated_data)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Customer Orders'])
class CustomerOrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsOrderCustomer]

    def get_object(self, request, pk):
        order = CustomerOrderService.get_owned_order(request.user, pk)
        self.check_object_permissions(request, order)
        return order

    @extend_schema(summary='Retrieve my order', responses=OrderSerializer)
    def get(self, request, pk):
        order = self.get_object(request, pk)
        return Response(OrderSerializer(order).data)

    @extend_schema(summary='Modify my order', request=CustomerOrderUpdateSerializer, responses=OrderSerializer)
    def patch(self, request, pk):
        order = self.get_object(request, pk)
        serializer = CustomerOrderUpdateSerializer(order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        order = CustomerOrderService.update_order(order, serializer.validated_data)
        return Response(OrderSerializer(order).data)


@extend_schema(tags=['Customer Orders'])
class CustomerOrderCancelAPIView(APIView):
    permission_classes = [IsAuthenticated, IsOrderCustomer]

    @extend_schema(summary='Cancel my order', request=None, responses=OrderSerializer)
    def post(self, request, pk):
        order = CustomerOrderService.get_owned_order(request.user, pk)
        self.check_object_permissions(request, order)
        order = CustomerOrderService.cancel_order(order)
        return Response(OrderSerializer(order).data)


def _parse_window_size(request):
    raw = request.query_params.get('window_size', 10)
    try:
        window_size = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({'window_size': 'Must be an integer.'})
    if window_size < 1:
        raise ValidationError({'window_size': 'Must be at least 1.'})
    return window_size


def _parse_statuses(request):
    raw = request.query_params.get('status')
    if raw is None:
        return None
    valid = set(Order.Status.values)
    statuses = [s.strip() for s in raw.split(',') if s.strip()]
    if not statuses:
        raise ValidationError({'status': 'Must include at least one status.'})
    invalid = [s for s in statuses if s not in valid]
    if invalid:
        raise ValidationError({'status': f'Invalid status value(s): {", ".join(invalid)}. Valid: {", ".join(sorted(valid))}.'})
    return statuses


def _parse_is_indoor(request):
    raw = request.query_params.get('is_indoor')
    if raw is None:
        return None
    value = str(raw).lower()
    if value in ('true', '1'):
        return True
    if value in ('false', '0'):
        return False
    raise ValidationError({'is_indoor': 'Must be true or false.'})
