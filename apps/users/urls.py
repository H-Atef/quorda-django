from django.urls import path
from apps.users.views import auth_views, user_views, restaurant_profile_views, cashier_views

urlpatterns = [
    path('auth/register/', auth_views.RegisterView.as_view(), name='register'),
    path('auth/login/', auth_views.LoginView.as_view(), name='login'),
    path('auth/refresh/', auth_views.RefreshView.as_view(), name='token-refresh'),
    path('auth/logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Users
    path('users/', user_views.UserListView.as_view(), name='user-list'),
    path('users/me/', user_views.UserDetailView.as_view(), name='user-detail'),

    # Cashiers (owner only)
    path('cashiers/', cashier_views.CashierListCreateView.as_view(), name='cashier-list-create'),
    path('cashiers/set-vip-permission/', cashier_views.CashierSetVipPermissionView.as_view(), name='cashier-set-vip-permission'),
    path('cashiers/<uuid:pk>/', cashier_views.CashierDetailView.as_view(), name='cashier-detail'),

    # Restaurant profiles
    path(
        'restaurant-profiles/',
        restaurant_profile_views.RestaurantProfileOwnerView.as_view(),
        name='restaurant-profile-owner',
    ),
    path(
        'restaurant-profiles/<uuid:user_id>/',
        restaurant_profile_views.RestaurantProfileAdminView.as_view(),
        name='restaurant-profile-admin',
    ),
]
