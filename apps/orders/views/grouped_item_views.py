from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.common.pagination import paginate
from apps.orders.permissions import IsRestaurantOwner
from apps.orders.serializers import ItemGroupSerializer
from apps.orders.services.item_grouping_service import (
    DEFAULT_BATCH_LIMIT, ItemGroupingService,
)
from apps.orders.views.order_views import (
    IS_INDOOR_PARAM, PAGE_PARAM, PAGE_SIZE_PARAM, SCOPE_PARAM, WINDOWED_PARAM,
)
from apps.orders.views.query_params import (
    parse_batch_limit, parse_bool, parse_is_indoor, parse_page, parse_page_size, parse_scope,
)
from apps.users.helpers.restaurant import get_user_restaurant

GROUPED_BATCH_LIMIT_PARAM = OpenApiParameter(
    name='batch_limit', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, default=DEFAULT_BATCH_LIMIT,
    description=(
        'Only group orders from the first N batches (windowed mode). Default 1 = the batch '
        'being cooked now. Use a larger number to look further ahead.'
    ),
)

_SCOPE_TO_VIP_ONLY = {'all': None, 'vip': True, 'normal': False}


def parse_grouping_filters(request) -> dict:
    """Turn the query string into the keyword arguments of ItemGroupingService."""
    return {
        'windowed': parse_bool(request, 'windowed', default=True),
        'batch_limit': parse_batch_limit(request, default=DEFAULT_BATCH_LIMIT),
        'vip_only': _SCOPE_TO_VIP_ONLY[parse_scope(request, default='all')],
        'is_indoor': parse_is_indoor(request),
    }


@extend_schema(tags=['Orders'])
class GroupedItemsAPIView(APIView):
    """Prep list: identical items from different orders, grouped and tagged with their orders."""
    permission_classes = [IsAuthenticated, IsRestaurantOwner]
    serializer_class = ItemGroupSerializer

    @extend_schema(
        summary='Group identical items across queued orders',
        description=(
            'Groups the same menu item from different pending orders so it can be cooked '
            'together, and lists which order needs how many. Orders keep their queue '
            'position and batch, so fairness stays visible. Groups are sorted by the '
            'earliest queue position that needs the item. The queue itself is never changed.'
        ),
        parameters=[
            WINDOWED_PARAM, GROUPED_BATCH_LIMIT_PARAM, SCOPE_PARAM, IS_INDOOR_PARAM,
            PAGE_PARAM, PAGE_SIZE_PARAM,
        ],
        responses=ItemGroupSerializer(many=True),
    )
    def get(self, request):
        restaurant = get_user_restaurant(request.user)
        page = parse_page(request)
        page_size = parse_page_size(request)
        prep_list = ItemGroupingService.get_prep_list(restaurant, **parse_grouping_filters(request))
        groups, meta = paginate(prep_list.groups, page, page_size)
        return Response({
            'orders_considered': prep_list.orders_considered,
            'results': ItemGroupSerializer(groups, many=True).data,
            **meta,
        })
