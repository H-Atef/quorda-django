from django.urls import path
from apps.orders.views import (
    OrderListCreateAPIView,
    OrderDetailAPIView,
    VIPOrdersAPIView,
    IndoorNormalWindowedAPIView,
    OutdoorNormalWindowedAPIView,
    SimpleOrdersAPIView,
    FilteredOrdersAPIView,
    RebalanceBatchesAPIView,
    BatchSummaryAPIView,
    ResetBatchesAPIView,
    CustomerOrderListCreateAPIView,
    CustomerOrderDetailAPIView,
    CustomerOrderCancelAPIView,
    OrderItemListCreateAPIView,
    OrderItemDetailAPIView,
    GroupedItemsAPIView,
)

urlpatterns = [
    # ---- restaurant-owner routes ----
    path('', OrderListCreateAPIView.as_view(), name='order-list-create'),
    path('vip/', VIPOrdersAPIView.as_view(), name='order-vip'),
    path('indoor/normal/windowed/', IndoorNormalWindowedAPIView.as_view(), name='order-indoor-normal-windowed'),
    path('outdoor/normal/windowed/', OutdoorNormalWindowedAPIView.as_view(), name='order-outdoor-normal-windowed'),
    path('filtered/', FilteredOrdersAPIView.as_view(), name='order-filtered'),
    path('simple/', SimpleOrdersAPIView.as_view(), name='order-simple'),
    path('items/grouped/', GroupedItemsAPIView.as_view(), name='order-items-grouped'),

    # ---- batch management ----
    path('batch/rebalance/', RebalanceBatchesAPIView.as_view(), name='batch-rebalance'),
    path('batch/reset/', ResetBatchesAPIView.as_view(), name='batch-reset'),
    path('batch/summary/', BatchSummaryAPIView.as_view(), name='batch-summary'),

    # ---- customer routes (delivery orders) ----
    path('customers/', CustomerOrderListCreateAPIView.as_view(), name='customer-order-list-create'),
    path('customers/<uuid:pk>/', CustomerOrderDetailAPIView.as_view(), name='customer-order-detail'),
    path('customers/<uuid:pk>/cancel/', CustomerOrderCancelAPIView.as_view(), name='customer-order-cancel'),

    # ---- restaurant-owner order detail / items ----
    path('<uuid:pk>/', OrderDetailAPIView.as_view(), name='order-detail'),
    path('<uuid:order_pk>/items/', OrderItemListCreateAPIView.as_view(), name='order-item-list-create'),
    path('<uuid:order_pk>/items/<uuid:pk>/', OrderItemDetailAPIView.as_view(), name='order-item-detail'),
]