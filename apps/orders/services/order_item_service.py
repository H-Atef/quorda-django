from rest_framework.exceptions import ValidationError

from apps.orders.models import Order, OrderItem
from apps.orders.services.order_service import _cache_items, _make_items, _assert_can_set_vip
from apps.users.helpers.constants import UserRole


EDITABLE_ORDER_STATUSES = (Order.Status.PENDING,)


class OrderItemService:
    """Business logic for order item operations."""

    @staticmethod
    def _assert_editable(order):
        if order.status not in EDITABLE_ORDER_STATUSES:
            raise ValidationError(f'Cannot modify an order that is "{order.status}". Only pending orders can be modified.')

    @staticmethod
    def add_item(order, validated_data):
        OrderItemService._assert_editable(order)
        menu_item = validated_data['menu_item']
        item = OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            quantity=validated_data['quantity'],
            unit_price=menu_item.price if menu_item is not None else None,
        )
        order.recalculate_priority_score(items=_cache_items(order))
        return item

    @staticmethod
    def update_item(item, validated_data, actor=None):
        OrderItemService._assert_editable(item.order)
        if 'menu_item' in validated_data:
            menu_item = validated_data['menu_item']
            item.menu_item = menu_item
            item.unit_price = menu_item.price if menu_item is not None else item.unit_price
        if 'quantity' in validated_data:
            item.quantity = validated_data['quantity']
        item.save()
        item.order.recalculate_priority_score(items=_cache_items(item.order))
        return item

    @staticmethod
    def delete_item(item, actor=None):
        OrderItemService._assert_editable(item.order)
        order = item.order
        item.delete()
        order.recalculate_priority_score(items=_cache_items(order))