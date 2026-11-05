from django.urls import path
from apps.restaurants.views import (
    RestaurantListView, RestaurantDetailView, RestaurantMenuItemsView,
    CategoryListCreateView, CategoryDetailView,
    MenuItemListCreateView, MenuItemDetailView,
    CriteriaView,
    CalculationParamsView,
    ShiftDefinitionListCreateView, ShiftDefinitionDetailView,
)

urlpatterns = [
    # Public: restaurants
    path('', RestaurantListView.as_view(), name='public-restaurant-list'),
    path('<uuid:pk>/', RestaurantDetailView.as_view(), name='public-restaurant-detail'),
    path('<uuid:pk>/menu-items/', RestaurantMenuItemsView.as_view(), name='public-restaurant-menu-items'),

    # Categories (owner only)
    path('categories/', CategoryListCreateView.as_view(), name='restaurant-category-list'),
    path('categories/<uuid:pk>/', CategoryDetailView.as_view(), name='restaurant-category-detail'),

    # Menu items (owner only)
    path('menu-items/', MenuItemListCreateView.as_view(), name='restaurant-menuitem-list'),
    path('menu-items/<uuid:pk>/', MenuItemDetailView.as_view(), name='restaurant-menuitem-detail'),

    # Criteria (owner only)
    path('criteria/', CriteriaView.as_view(), name='restaurant-criteria'),

    # Calculation params (owner only)
    path('api/v1/restaurants/calculation-params/', CalculationParamsView.as_view(), name='calculation-params'),

    # Shifts (owner only)
    path('shifts/', ShiftDefinitionListCreateView.as_view(), name='restaurant-shift-list-create'),
    path('shifts/<uuid:pk>/', ShiftDefinitionDetailView.as_view(), name='restaurant-shift-detail'),
]
