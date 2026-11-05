from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound

from apps.restaurants.permissions import IsRestaurantOwner, IsRestaurantOwnerOnly
from apps.restaurants.serializers import (
    CategorySerializer, MenuItemSerializer, CriteriaSerializer, CalculationParamsSerializer,
    PublicRestaurantProfileSerializer, ShiftDefinitionSerializer,
)
from apps.restaurants.services import (
    CategoryService, MenuItemService, CriteriaService, CalculationParamsService,
    PublicRestaurantsService, ShiftDefinitionService,
)
from apps.users.helpers.restaurant import get_user_restaurant




# ─────────────────────────── Public: Restaurants ────────────────────────────

class RestaurantListView(APIView):
     
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['public-restaurants'],
        operation_id='v1_public_restaurants_list',
        summary='List all active restaurants',
        responses={200: OpenApiResponse(response=PublicRestaurantProfileSerializer(many=True))},
    )
    def get(self, request):
        restaurants = PublicRestaurantsService.list_active_restaurants()
        return Response(PublicRestaurantProfileSerializer(restaurants, many=True).data)


class RestaurantDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['public-restaurants'],
        operation_id='v1_public_restaurants_retrieve',
        summary='Retrieve a restaurant by ID',
        responses={
            200: OpenApiResponse(response=PublicRestaurantProfileSerializer),
            404: OpenApiResponse(description='Restaurant not found'),
        },
    )
    def get(self, request, pk):
        restaurant = PublicRestaurantsService.get_active_restaurant(pk)
        return Response(PublicRestaurantProfileSerializer(restaurant).data)


class RestaurantMenuItemsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['public-restaurants'],
        operation_id='v1_public_restaurant_menu_items',
        summary='List all available menu items for a specific restaurant',
        responses={
            200: OpenApiResponse(response=MenuItemSerializer(many=True)),
            404: OpenApiResponse(description='Restaurant not found'),
        },
    )
    def get(self, request, pk):
        items = PublicRestaurantsService.list_menu_items(pk)
        return Response(MenuItemSerializer(items, many=True).data)


# ─────────────────────────── Categories ────────────────────────────

@extend_schema(tags=['restaurant-categories'])
class CategoryListCreateView(APIView):

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsRestaurantOwner()]
        return [IsRestaurantOwnerOnly()]

    @extend_schema(
        tags=['restaurant-categories'],
        operation_id='v1_restaurants_categories_list',
        summary='List categories',
        description='Returns all categories belonging to the authenticated restaurant.',
        responses={200: OpenApiResponse(response=CategorySerializer(many=True))},
    )
    def get(self, request):
        profile = get_user_restaurant(request.user)
        categories = CategoryService.list_for_restaurant(profile)
        return Response(CategorySerializer(categories, many=True).data)

    @extend_schema(
        tags=['restaurant-categories'],
        operation_id='v1_restaurants_categories_create',
        summary='Create a category',
        request=CategorySerializer,
        responses={
            201: OpenApiResponse(response=CategorySerializer),
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        profile = get_user_restaurant(request.user)
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = CategoryService.create(profile, serializer.validated_data)
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['restaurant-categories'])
class CategoryDetailView(APIView):

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsRestaurantOwner()]
        return [IsRestaurantOwnerOnly()]

    def _get_category(self, request, pk):
        return CategoryService.get_by_id(pk, get_user_restaurant(request.user))

    @extend_schema(
        tags=['restaurant-categories'],
        operation_id='v1_restaurants_categories_retrieve',
        summary='Retrieve a category',
        responses={200: OpenApiResponse(response=CategorySerializer), 404: OpenApiResponse(description='Not found')},
    )
    def get(self, request, pk):
        return Response(CategorySerializer(self._get_category(request, pk)).data)

    @extend_schema(
        tags=['restaurant-categories'],
        operation_id='v1_restaurants_categories_update',
        summary='Update a category (full)',
        request=CategorySerializer,
        responses={200: OpenApiResponse(response=CategorySerializer), 400: OpenApiResponse(description='Validation error')},
    )
    def put(self, request, pk):
        category = self._get_category(request, pk)
        serializer = CategorySerializer(category, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = CategoryService.update(category, serializer.validated_data)
        return Response(CategorySerializer(updated).data)

    @extend_schema(
        tags=['restaurant-categories'],
        operation_id='v1_restaurants_categories_partial_update',
        summary='Partial update a category',
        request=CategorySerializer,
        responses={200: OpenApiResponse(response=CategorySerializer)},
    )
    def patch(self, request, pk):
        category = self._get_category(request, pk)
        serializer = CategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = CategoryService.update(category, serializer.validated_data, partial=True)
        return Response(CategorySerializer(updated).data)

    @extend_schema(
        tags=['restaurant-categories'],
        operation_id='v1_restaurants_categories_delete',
        summary='Delete a category',
        responses={204: OpenApiResponse(description='Deleted')},
    )
    def delete(self, request, pk):
        CategoryService.delete(self._get_category(request, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────── Menu Items ────────────────────────────

@extend_schema(tags=['restaurant-menu-items'])
class MenuItemListCreateView(APIView):

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsRestaurantOwner()]
        return [IsRestaurantOwnerOnly()]

    @extend_schema(
        tags=['restaurant-menu-items'],
        operation_id='v1_restaurants_menu_items_list',
        summary='List menu items',
        description='Returns all menu items of the authenticated restaurant. Category is optional.',
        responses={200: OpenApiResponse(response=MenuItemSerializer(many=True))},
    )
    def get(self, request):
        profile = get_user_restaurant(request.user)
        items = MenuItemService.list_for_restaurant(profile)
        return Response(MenuItemSerializer(items, many=True).data)

    @extend_schema(
        tags=['restaurant-menu-items'],
        operation_id='v1_restaurants_menu_items_create',
        summary='Create a menu item',
        request=MenuItemSerializer,
        responses={
            201: OpenApiResponse(response=MenuItemSerializer),
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        profile = get_user_restaurant(request.user)
        serializer = MenuItemSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = MenuItemService.create(profile, serializer.validated_data)
        return Response(MenuItemSerializer(item).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['restaurant-menu-items'])
class MenuItemDetailView(APIView):

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsRestaurantOwner()]
        return [IsRestaurantOwnerOnly()]

    def _get_item(self, request, pk):
        return MenuItemService.get_by_id(pk, get_user_restaurant(request.user))

    @extend_schema(
        tags=['restaurant-menu-items'],
        operation_id='v1_restaurants_menu_items_retrieve',
        summary='Retrieve a menu item',
        responses={200: OpenApiResponse(response=MenuItemSerializer), 404: OpenApiResponse(description='Not found')},
    )
    def get(self, request, pk):
        return Response(MenuItemSerializer(self._get_item(request, pk)).data)

    @extend_schema(
        tags=['restaurant-menu-items'],
        operation_id='v1_restaurants_menu_items_update',
        summary='Update a menu item (full)',
        request=MenuItemSerializer,
        responses={200: OpenApiResponse(response=MenuItemSerializer)},
    )
    def put(self, request, pk):
        item = self._get_item(request, pk)
        serializer = MenuItemSerializer(item, data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        updated = MenuItemService.update(item, serializer.validated_data)
        return Response(MenuItemSerializer(updated).data)

    @extend_schema(
        tags=['restaurant-menu-items'],
        operation_id='v1_restaurants_menu_items_partial_update',
        summary='Partial update a menu item',
        request=MenuItemSerializer,
        responses={200: OpenApiResponse(response=MenuItemSerializer)},
    )
    def patch(self, request, pk):
        item = self._get_item(request, pk)
        serializer = MenuItemSerializer(item, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        updated = MenuItemService.update(item, serializer.validated_data, partial=True)
        return Response(MenuItemSerializer(updated).data)

    @extend_schema(
        tags=['restaurant-menu-items'],
        operation_id='v1_restaurants_menu_items_delete',
        summary='Delete a menu item',
        responses={204: OpenApiResponse(description='Deleted')},
    )
    def delete(self, request, pk):
        MenuItemService.delete(self._get_item(request, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────── Criteria ────────────────────────────

@extend_schema(tags=['restaurant-criteria'])
class CriteriaView(APIView):

    permission_classes = [IsRestaurantOwnerOnly]

    @extend_schema(
        tags=['restaurant-criteria'],
        operation_id='v1_restaurants_criteria_retrieve',
        summary='Get criteria',
        responses={
            200: OpenApiResponse(response=CriteriaSerializer),
            404: OpenApiResponse(description='No criteria configured yet'),
        },
    )
    def get(self, request):
        profile = get_user_restaurant(request.user)
        criteria = CriteriaService.get_or_none(profile)
        if criteria is None:
            return Response(
                {'detail': 'No criteria configured yet for this restaurant.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(CriteriaSerializer(criteria).data)

    @extend_schema(
        tags=['restaurant-criteria'],
        operation_id='v1_restaurants_criteria_create_or_update',
        summary='Create or update criteria',
        request=CriteriaSerializer,
        responses={
            200: OpenApiResponse(response=CriteriaSerializer, description='Updated'),
            201: OpenApiResponse(response=CriteriaSerializer, description='Created'),
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        profile = get_user_restaurant(request.user)
        serializer = CriteriaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        criteria, created = CriteriaService.create_or_update(profile, serializer.validated_data)
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(CriteriaSerializer(criteria).data, status=http_status)

    @extend_schema(
        tags=['restaurant-criteria'],
        operation_id='v1_restaurants_criteria_delete',
        summary='Delete criteria',
        responses={
            204: OpenApiResponse(description='Deleted successfully'),
            404: OpenApiResponse(description='No criteria configured'),
        },
    )
    def delete(self, request):
        profile = get_user_restaurant(request.user)
        criteria = CriteriaService.get_or_none(profile)
        if criteria is None:
            raise NotFound('No criteria configured for this restaurant.')
        CriteriaService.delete(criteria)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────── Calculation Params ────────────────────────────



@extend_schema(tags=['restaurant-calculation-params'])
class CalculationParamsView(APIView):
    permission_classes = [IsRestaurantOwnerOnly]

    @extend_schema(
        operation_id='v1_restaurants_calculation_params_get',
        summary='Retrieve calculation params for authenticated restaurant',
        responses={
            200: OpenApiResponse(response=CalculationParamsSerializer),
            404: OpenApiResponse(description='No params configured'),
        },
    )
    def get(self, request):
        profile = get_user_restaurant(request.user)
        params = CalculationParamsService.get_for_restaurant(profile)
        return Response(CalculationParamsSerializer(params).data)

    @extend_schema(
        operation_id='v1_restaurants_calculation_params_create',
        summary='Create calculation params',
        request=CalculationParamsSerializer,
        responses={
            201: OpenApiResponse(response=CalculationParamsSerializer),
            400: OpenApiResponse(description='Validation error'),
            409: OpenApiResponse(description='Params already exist (use PUT to update)'),
        },
    )
    def post(self, request):
        profile = get_user_restaurant(request.user)
        # Check if already exists
        try:
            CalculationParamsService.get_for_restaurant(profile)
            return Response(
                {"detail": "Params already exist. Use PUT or PATCH to update."},
                status=status.HTTP_409_CONFLICT
            )
        except NotFound:
            pass  # proceed to create

        serializer = CalculationParamsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = CalculationParamsService.create(profile, serializer.validated_data)
        return Response(CalculationParamsSerializer(params).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id='v1_restaurants_calculation_params_update',
        summary='Full update calculation params',
        request=CalculationParamsSerializer,
        responses={
            200: OpenApiResponse(response=CalculationParamsSerializer),
            400: OpenApiResponse(description='Validation error'),
            404: OpenApiResponse(description='No params configured'),
        },
    )
    def put(self, request):
        profile = get_user_restaurant(request.user)
        params = CalculationParamsService.get_for_restaurant(profile)
        serializer = CalculationParamsSerializer(params, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = CalculationParamsService.update(params, serializer.validated_data)
        return Response(CalculationParamsSerializer(updated).data)

    @extend_schema(
        operation_id='v1_restaurants_calculation_params_partial_update',
        summary='Partial update calculation params',
        request=CalculationParamsSerializer,
        responses={
            200: OpenApiResponse(response=CalculationParamsSerializer),
            400: OpenApiResponse(description='Validation error'),
            404: OpenApiResponse(description='No params configured'),
        },
    )
    def patch(self, request):
        profile = get_user_restaurant(request.user)
        params = CalculationParamsService.get_for_restaurant(profile)
        serializer = CalculationParamsSerializer(params, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = CalculationParamsService.update(params, serializer.validated_data, partial=True)
        return Response(CalculationParamsSerializer(updated).data)

    @extend_schema(
        operation_id='v1_restaurants_calculation_params_delete',
        summary='Delete calculation params',
        responses={
            204: OpenApiResponse(description='Deleted'),
            404: OpenApiResponse(description='No params configured'),
        },
    )
    def delete(self, request):
        profile = get_user_restaurant(request.user)
        params = CalculationParamsService.get_for_restaurant(profile)
        CalculationParamsService.delete(params)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────── Shifts ────────────────────────────


@extend_schema(tags=['restaurant-shifts'])
class ShiftDefinitionListCreateView(APIView):
    permission_classes = [IsRestaurantOwnerOnly]

    @extend_schema(operation_id='v1_restaurants_shifts_list', responses=ShiftDefinitionSerializer(many=True))
    def get(self, request):
        profile = get_user_restaurant(request.user)
        return Response(ShiftDefinitionSerializer(ShiftDefinitionService.list_for_restaurant(profile), many=True).data)

    @extend_schema(operation_id='v1_restaurants_shifts_create', request=ShiftDefinitionSerializer, responses={201: ShiftDefinitionSerializer})
    def post(self, request):
        profile = get_user_restaurant(request.user)
        serializer = ShiftDefinitionSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        shift = ShiftDefinitionService.create(profile, serializer.validated_data)
        return Response(ShiftDefinitionSerializer(shift).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['restaurant-shifts'])
class ShiftDefinitionDetailView(APIView):
    permission_classes = [IsRestaurantOwnerOnly]

    def _get_shift(self, request, pk):
        return ShiftDefinitionService.get_by_id(pk, get_user_restaurant(request.user))

    @extend_schema(operation_id='v1_restaurants_shifts_retrieve', responses=ShiftDefinitionSerializer)
    def get(self, request, pk):
        return Response(ShiftDefinitionSerializer(self._get_shift(request, pk)).data)

    @extend_schema(operation_id='v1_restaurants_shifts_update', request=ShiftDefinitionSerializer, responses=ShiftDefinitionSerializer)
    def put(self, request, pk):
        shift = self._get_shift(request, pk)
        serializer = ShiftDefinitionSerializer(shift, data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(ShiftDefinitionSerializer(ShiftDefinitionService.update(shift, serializer.validated_data)).data)

    @extend_schema(operation_id='v1_restaurants_shifts_partial_update', request=ShiftDefinitionSerializer, responses=ShiftDefinitionSerializer)
    def patch(self, request, pk):
        shift = self._get_shift(request, pk)
        serializer = ShiftDefinitionSerializer(shift, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(ShiftDefinitionSerializer(ShiftDefinitionService.update(shift, serializer.validated_data, partial=True)).data)

    @extend_schema(operation_id='v1_restaurants_shifts_delete', responses={204: None})
    def delete(self, request, pk):
        ShiftDefinitionService.deactivate(self._get_shift(request, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)