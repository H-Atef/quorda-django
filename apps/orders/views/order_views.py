from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.orders.permissions import IsRestaurantOwner
from apps.orders.serializers import OrderSerializer, OrderListSerializer, OrderWriteSerializer
from apps.orders.services.order_service import OrderService
from apps.orders.views.query_params import (
    parse_bool, parse_is_indoor, parse_limit, parse_scope,
    parse_statuses, parse_page, parse_page_size,
    parse_batch_limit, parse_ordering,
)
from apps.common.pagination import paginate
from apps.users.helpers.restaurant import get_user_restaurant


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
PAGE_PARAM = OpenApiParameter(
    name='page', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, default=1, description='Page number.',
)
PAGE_SIZE_PARAM = OpenApiParameter(
    name='page_size', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, default=20, description='Number of items per page.',
)
BATCH_LIMIT_PARAM = OpenApiParameter(
    name='batch_limit', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, description='Max number of batches to return.',
)
ORDERING_PARAM = OpenApiParameter(
    name='ordering', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY,
    required=False,
    description='Ordering field(s), e.g. "-created_at" or "priority_score".',
)


@extend_schema(tags=['Orders'])
class OrderListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        summary='List orders',
        parameters=[PAGE_PARAM, PAGE_SIZE_PARAM, ORDERING_PARAM],
        responses=OrderListSerializer(many=True),
    )
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        page = parse_page(request)
        page_size = parse_page_size(request)
        ordering = parse_ordering(
            request,
            allowed={'batch_number', 'created_at', 'priority_score', 'special_flag', 'status', 'is_indoor'},
        )
        qs = OrderService.get_restaurant_orders_qs(restaurant)
        if ordering:
            qs = qs.order_by(*[f.strip() for f in ordering.split(',') if f.strip()])
        else:
            qs = qs.order_by('-created_at')
        items, meta = paginate(qs, page, page_size)
        return Response({'results': OrderListSerializer(items, many=True).data, **meta})

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

    @extend_schema(
        parameters=[PAGE_PARAM, PAGE_SIZE_PARAM, BATCH_LIMIT_PARAM, ORDERING_PARAM],
    )
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        page = parse_page(request)
        page_size = parse_page_size(request)
        batch_limit = parse_batch_limit(request) or 5  # Default: first 5 batches only
        ordering = parse_ordering(
            request,
            allowed={'batch_number', 'created_at', 'priority_score', 'special_flag', 'status', 'is_indoor'},
        )
        orders = OrderService.list_orders_qs(
            restaurant,
            vip_only=True,
            windowed=True,
            batch_limit=batch_limit,
            ordering=ordering,
        )
        items, meta = paginate(orders, page, page_size)
        return Response({'results': OrderListSerializer(items, many=True).data, **meta})


@extend_schema(tags=['Orders'])
class IndoorNormalWindowedAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        parameters=[PAGE_PARAM, PAGE_SIZE_PARAM, BATCH_LIMIT_PARAM, ORDERING_PARAM],
    )
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        page = parse_page(request)
        page_size = parse_page_size(request)
        batch_limit = parse_batch_limit(request) or 5  # Default: first 5 batches only
        ordering = parse_ordering(
            request,
            allowed={'batch_number', 'created_at', 'priority_score', 'special_flag', 'status', 'is_indoor'},
        )
        orders = OrderService.get_indoor_normal_windowed_qs(restaurant)
        items, meta = paginate(orders, page, page_size)
        return Response({'results': OrderListSerializer(items, many=True).data, **meta})


@extend_schema(tags=['Orders'])
class OutdoorNormalWindowedAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        parameters=[PAGE_PARAM, PAGE_SIZE_PARAM, BATCH_LIMIT_PARAM, ORDERING_PARAM],
    )
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        page = parse_page(request)
        page_size = parse_page_size(request)
        batch_limit = parse_batch_limit(request) or 5  # Default: first 5 batches only
        ordering = parse_ordering(
            request,
            allowed={'batch_number', 'created_at', 'priority_score', 'special_flag', 'status', 'is_indoor'},
        )
        orders = OrderService.get_outdoor_normal_windowed_qs(restaurant)
        items, meta = paginate(orders, page, page_size)
        return Response({'results': OrderListSerializer(items, many=True).data, **meta})


@extend_schema(tags=['Orders'])
class SimpleOrdersAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        parameters=[PAGE_PARAM, PAGE_SIZE_PARAM, ORDERING_PARAM],
    )
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        page = parse_page(request)
        page_size = parse_page_size(request)
        ordering = parse_ordering(
            request,
            allowed={'batch_number', 'created_at', 'priority_score', 'special_flag', 'status', 'is_indoor'},
        )
        orders = OrderService.get_simple_orders_qs(restaurant)
        if ordering:
            orders = _apply_ordering(orders, ordering)
        items, meta = paginate(orders, page, page_size)
        return Response({'results': OrderListSerializer(items, many=True).data, **meta})


@extend_schema(tags=['Orders'])
class FilteredOrdersAPIView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        summary='Filter/sort orders by any combination',
        parameters=[SCOPE_PARAM, STATUS_PARAM, IS_INDOOR_PARAM, WINDOWED_PARAM, LIMIT_PARAM, PAGE_PARAM, PAGE_SIZE_PARAM, BATCH_LIMIT_PARAM, ORDERING_PARAM],
    )
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        scope = parse_scope(request, default='all')
        vip_only = {'all': None, 'vip': True, 'normal': False}[scope]
        page = parse_page(request)
        page_size = parse_page_size(request)
        batch_limit = parse_batch_limit(request) or 5  # Default: first 5 batches only
        ordering = parse_ordering(
            request,
            allowed={'batch_number', 'created_at', 'priority_score', 'special_flag', 'status', 'is_indoor'},
        )
        orders = OrderService.list_orders_qs(
            restaurant,
            vip_only=vip_only,
            is_indoor=parse_is_indoor(request),
            statuses=parse_statuses(request),
            windowed=parse_bool(request, 'windowed', default=True),
            limit=parse_limit(request),
            batch_limit=batch_limit,
            ordering=ordering,
        )
        items, meta = paginate(orders, page, page_size)
        return Response({'results': OrderListSerializer(items, many=True).data, **meta})


def _apply_ordering(orders, ordering):
    """Apply ordering to the simple-orders queryset in SQL.

    Equivalent to the previous in-Python stable multi-pass sort over a list
    that was already ordered by created_at: the requested fields win, and
    created_at ASC breaks ties. Done in the DB so only one page is loaded.
    """
    fields = [f.strip() for f in ordering.split(',') if f.strip()]
    return orders.order_by(*fields, 'created_at')
