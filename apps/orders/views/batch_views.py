from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.orders.permissions import IsRestaurantOwner
from apps.orders.serializers import OrderSerializer
from apps.orders.services.order_service import OrderService
from apps.orders.views.query_params import parse_int, parse_window_size
from apps.users.helpers.restaurant import get_user_restaurant


WINDOW_SIZE_PARAM = OpenApiParameter(
    name='window_size', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, default=10, description='Batch size target.',
)
BATCH_PARAM = OpenApiParameter(
    name='batch', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, description='Specific batch number to rebalance (optional).',
)
MODE_PARAM = OpenApiParameter(
    name='mode', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY,
    required=False, enum=['completed', 'all'], default='completed',
    description='Reset mode: "completed" (default, safe) resets only done/cancelled orders; "all" resets everything but requires no pending orders.',
)


@extend_schema(tags=['Batch Management'])
class RebalanceBatchesAPIView(APIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        summary='Rebalance batches (promote oldest from later into holes)',
        parameters=[WINDOW_SIZE_PARAM, BATCH_PARAM],
    )
    def post(self, request):
        restaurant = get_user_restaurant(request.user)
        window_size = parse_window_size(request)
        target_batch = parse_int(request, 'batch', default=None, minimum=1)
        return Response(OrderService.rebalance_batches(
            restaurant, window_size=window_size, target_batch=target_batch,
        ))


@extend_schema(tags=['Batch Management'])
class BatchSummaryAPIView(APIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(summary='Pending count per batch', parameters=[WINDOW_SIZE_PARAM])
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        window_size = parse_window_size(request)
        summary = OrderService._batch_summary(restaurant)
        for row in summary:
            row['holes'] = max(0, window_size - row['pending'])
        return Response(summary)


@extend_schema(tags=['Batch Management'])
class ResetBatchesAPIView(APIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(summary='Reset batch numbers', parameters=[MODE_PARAM])
    def post(self, request):
        restaurant = get_user_restaurant(request.user)
        mode = (request.query_params.get('mode') or 'completed').lower()
        return Response(OrderService.reset_batches(restaurant, mode=mode))