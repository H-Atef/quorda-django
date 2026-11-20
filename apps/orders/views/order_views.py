from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.orders.permissions import IsRestaurantOwner
from apps.orders.serializers import OrderSerializer, OrderWriteSerializer
from apps.orders.services.order_service import OrderService
from apps.orders.views.query_params import parse_int, parse_bool, parse_is_indoor, parse_limit, parse_scope, parse_statuses, parse_window_size
from apps.users.helpers.restaurant import get_user_restaurant


WINDOW_SIZE_PARAM = OpenApiParameter(
    name='window_size', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, default=10, description='Batch size target.',
)
SCOPE_PARAM = OpenApiParameter(
    name='scope', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY,
    required=False, enum=['all', 'vip', 'normal'],
)
STATUS_PARAM = OpenApiParameter(
    name='status', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY,
    required=False,
)
IS_INDOOR_PARAM = OpenApiParameter(
    name='is_indoor', type=OpenApiTypes.BOOL, location=OpenApiParameter.QUERY,
    required=False,
)
WINDOWED_PARAM = OpenApiParameter(
    name='windowed', type=OpenApiTypes.BOOL, location=OpenApiParameter.QUERY,
    required=False, default=True,
)
LIMIT_PARAM = OpenApiParameter(
    name='limit', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False,
)


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
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(parameters=[WINDOW_SIZE_PARAM])
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        orders = OrderService.get_vip_orders(restaurant)
        return Response(OrderSerializer(orders, many=True).data)


@extend_schema(tags=['Orders'])
class WindowedOrdersAPIView(APIView):
    """Legacy endpoint - returns all active orders (VIP + normal) windowed by batch."""
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(parameters=[WINDOW_SIZE_PARAM, STATUS_PARAM, IS_INDOOR_PARAM])
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        window_size = parse_window_size(request)
        statuses = parse_statuses(request)
        is_indoor = parse_is_indoor(request)
        orders = OrderService.get_windowed_orders(restaurant, window_size, statuses=statuses, is_indoor=is_indoor)
        return Response(OrderSerializer(orders, many=True).data)


@extend_schema(tags=['Orders'])
class IndoorNormalWindowedAPIView(APIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(parameters=[WINDOW_SIZE_PARAM])
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        orders = OrderService.get_indoor_normal_windowed(restaurant)
        return Response(OrderSerializer(orders, many=True).data)


@extend_schema(tags=['Orders'])
class OutdoorNormalWindowedAPIView(APIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(parameters=[WINDOW_SIZE_PARAM])
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        orders = OrderService.get_outdoor_normal_windowed(restaurant)
        return Response(OrderSerializer(orders, many=True).data)


@extend_schema(tags=['Orders'])
class SimpleOrdersAPIView(APIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema()
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        orders = OrderService.get_simple_orders(restaurant)
        return Response(OrderSerializer(orders, many=True).data)


@extend_schema(tags=['Orders'])
class FilteredOrdersAPIView(APIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        summary='Filter/sort orders by any combination',
        parameters=[SCOPE_PARAM, STATUS_PARAM, IS_INDOOR_PARAM, WINDOWED_PARAM, LIMIT_PARAM],
    )
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        scope = parse_scope(request, default='all')
        vip_only = {'all': None, 'vip': True, 'normal': False}[scope]
        orders = OrderService.list_orders(
            restaurant,
            vip_only=vip_only,
            is_indoor=parse_is_indoor(request),
            statuses=parse_statuses(request),
            windowed=parse_bool(request, 'windowed', default=True),
            limit=parse_limit(request),
        )
        return Response(OrderSerializer(orders, many=True).data)