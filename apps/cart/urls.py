from django.urls import path

from apps.cart import views

urlpatterns = [
    path('', views.CartAPIView.as_view(), name='cart'),
    path('items/', views.CartItemAddAPIView.as_view(), name='cart-item-add'),
    path(
        'items/<uuid:item_id>/',
        views.CartItemDetailAPIView.as_view(),
        name='cart-item-detail',
    ),
    path('checkout/', views.CartCheckoutAPIView.as_view(), name='cart-checkout'),
]
