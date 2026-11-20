from rest_framework.exceptions import ValidationError

from apps.orders.helpers.order_sorter import OrderSorter
from apps.orders.models import Order, OrderItem
from apps.orders.services.order_service import _make_items


EDITABLE_ORDER_STATUSES = (Order.Status.PENDING, Order.Status.PREPARING)


class CustomerOrderService:
    """Business logic for customer-facing delivery orders (is_indoor=False)."""

    @staticmethod
    def get_customer_orders_qs(customer):
        return (
            Order.objects.filter(customer=customer, is_indoor=False)
            .select_related('created_by', 'shift')
            .prefetch_related('order_items__menu_item__category')
        )

    @staticmethod
    def get_owned_order(customer, order_pk):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(
            Order.objects.select_related('created_by', 'shift')
            .prefetch_related('order_items__menu_item__category'),
            pk=order_pk,
            customer=customer,
            is_indoor=False,
        )

    @staticmethod
    def create_order(customer, restaurant, validated_data):
        if not restaurant.is_active:
            raise ValidationError({'restaurant': 'Cannot order from an inactive restaurant.'})
        items_data = validated_data.pop('order_items')
        order = Order.objects.create(
            restaurant=restaurant,
            customer=customer,
            created_by=customer,
            is_indoor=False,
            **validated_data,
        )
        OrderSorter.assign_batch_number(order, window_size=10)
        order.save(update_fields=['batch_number'])
        _make_items(order, items_data)
        order.recalculate_priority_score()
        return order

    @staticmethod
    def update_order(order, validated_data):
        if order.status not in EDITABLE_ORDER_STATUSES:
            raise ValidationError(
                f'Cannot modify an order that is already "{order.status}". '
                'Only pending or preparing orders can be modified.'
            )
        items_data = validated_data.pop('order_items', None)
        for attr, value in validated_data.items():
            setattr(order, attr, value)
        order.save()
        if items_data is not None:
            order.order_items.all().delete()
            _make_items(order, items_data)
            order.recalculate_priority_score()
        return order

    @staticmethod
    def cancel_order(order):
        if order.status in (Order.Status.DONE, Order.Status.CANCELLED):
            raise ValidationError(f'Cannot cancel an order that is already "{order.status}".')
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status', 'updated_at'])
        return order