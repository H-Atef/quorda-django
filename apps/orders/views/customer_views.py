from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.orders.permissions import IsOrderCustomer
from apps.orders.serializers import CustomerOrderCreateSerializer, CustomerOrderUpdateSerializer, OrderSerializer
from apps.orders.services.customer_order_service import CustomerOrderService
from apps.orders.views.query_params import parse_page, parse_page_size
from apps.common.pagination import paginate


PAGE_PARAM = OpenApiParameter(
    name='page', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, default=1, description='Page number.',
)
PAGE_SIZE_PARAM = OpenApiParameter(
    name='page_size', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, default=20, description='Number of items per page.',
)


@extend_schema(tags=['Customer Orders'])
class CustomerOrderListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='List my delivery orders',
        parameters=[PAGE_PARAM, PAGE_SIZE_PARAM],
        responses=OrderSerializer(many=True),
    )
    def get(self, request):
        page = parse_page(request)
        page_size = parse_page_size(request)
        qs = CustomerOrderService.get_customer_orders_qs(request.user)
        items, meta = paginate(qs, page, page_size)
        return Response({'results': OrderSerializer(items, many=True).data, **meta})

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