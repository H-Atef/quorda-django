from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.orders.helpers.order_sorter import OrderSorter
from apps.orders.helpers.simple_order_detector import SimpleOrderDetector
from apps.orders.models import Order, OrderItem
from apps.restaurants.services import CriteriaService
from apps.users.helpers.constants import UserRole

ACTIVE_ORDER_STATUSES = (Order.Status.PENDING, Order.Status.PREPARING)
EDITABLE_ORDER_STATUSES = (Order.Status.PENDING, Order.Status.PREPARING)


class Conflict(APIException):
    status_code = 409
    default_detail = 'Conflict.'
    default_code = 'conflict'


def _assert_can_set_vip(actor, current_flag, requested_flag):
    if requested_flag == current_flag:
        return
    if actor.role == UserRole.RESTAURANT:
        return
    if actor.role == UserRole.CASHIER:
        profile = getattr(actor, 'cashier_profile', None)
        if profile and profile.is_active and profile.can_set_vip:
            return
    raise PermissionDenied('You do not have permission to change the VIP flag.')


def _make_items(order, items_data):
    result = []
    for item in items_data:
        menu_item = item['menu_item']
        result.append(OrderItem(
            order=order,
            menu_item=menu_item,
            quantity=item['quantity'],
            unit_price=menu_item.price if menu_item is not None else None,
        ))
    return OrderItem.objects.bulk_create(result)


class OrderService:
    """Business logic for restaurant-owner/cashier order operations."""

    @staticmethod
    def get_restaurant_orders_qs(restaurant):
        return (
            Order.objects.filter(restaurant=restaurant)
            .select_related('created_by', 'shift')
            .prefetch_related('order_items__menu_item__category')
        )

    @staticmethod
    def get_owned_order(restaurant, order_pk):
        return get_object_or_404(
            Order.objects.select_related('created_by', 'shift')
            .prefetch_related('order_items__menu_item__category'),
            pk=order_pk,
            restaurant=restaurant,
        )

    @staticmethod
    def get_owned_item(restaurant, order_pk, item_pk):
        order = OrderService.get_owned_order(restaurant, order_pk)
        item = get_object_or_404(
            order.order_items.select_related('menu_item__category'),
            pk=item_pk,
        )
        return order, item

    @staticmethod
    def create_order(restaurant, validated_data, actor):
        items_data = validated_data.pop('order_items')
        requested_flag = bool(validated_data.get('special_flag', False))
        _assert_can_set_vip(actor, False, requested_flag)
        validated_data.pop('is_indoor', None)
        validated_data.pop('customer', None)
        validated_data.pop('created_by', None)
        validated_data.pop('shift', None)
        order = Order.objects.create(
            restaurant=restaurant,
            created_by=actor,
            is_indoor=True,
            **validated_data,
        )
        _make_items(order, items_data)
        order.recalculate_priority_score()
        return order

    @staticmethod
    def _assert_editable(order):
        if order.status not in EDITABLE_ORDER_STATUSES:
            raise Conflict(f'Cannot modify an order that is "{order.status}". Only pending or preparing orders can be modified.')

    @staticmethod
    def update_order(order, validated_data, actor):
        OrderService._assert_editable(order)
        items_data = validated_data.pop('order_items', None)
        if 'special_flag' in validated_data:
            requested_flag = bool(validated_data['special_flag'])
            _assert_can_set_vip(actor, order.special_flag, requested_flag)
        for attr, value in validated_data.items():
            if attr in ('is_indoor', 'customer', 'created_by', 'shift', 'restaurant'):
                continue
            setattr(order, attr, value)
        order.save()

        if items_data is not None:
            order.order_items.all().delete()
            _make_items(order, items_data)
            order.recalculate_priority_score()
        return order

    @staticmethod
    def delete_order(order, actor=None):
        order.delete()

    @staticmethod
    def cancel_order(order, actor=None):
        if order.status in (Order.Status.DONE, Order.Status.CANCELLED):
            raise Conflict(f'Cannot cancel an order that is already "{order.status}".')
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status', 'updated_at'])
        return order

    @staticmethod
    def add_item(order, validated_data):
        OrderService._assert_editable(order)
        menu_item = validated_data['menu_item']
        item = OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            quantity=validated_data['quantity'],
            unit_price=menu_item.price if menu_item is not None else None,
        )
        order.recalculate_priority_score()
        return item

    @staticmethod
    def update_item(item, validated_data, actor=None):
        OrderService._assert_editable(item.order)
        if 'menu_item' in validated_data:
            menu_item = validated_data['menu_item']
            item.menu_item = menu_item
            item.unit_price = menu_item.price if menu_item is not None else item.unit_price
        if 'quantity' in validated_data:
            item.quantity = validated_data['quantity']
        item.save()
        item.order.recalculate_priority_score()
        return item

    @staticmethod
    def delete_item(item, actor=None):
        OrderService._assert_editable(item.order)
        order = item.order
        item.delete()
        order.recalculate_priority_score()

    @staticmethod
    def _base_qs(restaurant, statuses, is_indoor):
        orders = OrderService.get_restaurant_orders_qs(restaurant)
        if statuses is None:
            statuses = ACTIVE_ORDER_STATUSES
        orders = orders.filter(status__in=statuses)
        if is_indoor is not None:
            orders = orders.filter(is_indoor=is_indoor)
        return list(orders)

    @staticmethod
    def get_vip_orders(restaurant):
        orders = OrderService.get_restaurant_orders_qs(restaurant)
        return OrderSorter.get_vip_orders(orders)

    @staticmethod
    def get_windowed_orders(restaurant, window_size, statuses=None, is_indoor=None):
        orders = OrderService._base_qs(restaurant, statuses, is_indoor)
        preparing = [o for o in orders if o.status == Order.Status.PREPARING]
        pending = [o for o in orders if o.status == Order.Status.PENDING]
        others = [o for o in orders if o.status not in (Order.Status.PREPARING, Order.Status.PENDING)]
        preparing = sorted(preparing, key=lambda o: o.created_at)
        pending_windowed = OrderSorter.sort_with_window(pending, window_size=window_size)
        others_sorted = OrderSorter.sort_with_window(others, window_size=window_size)
        return preparing + pending_windowed + others_sorted

    @staticmethod
    def get_normal_windowed_orders(restaurant, window_size, statuses=None, is_indoor=None):
        orders = OrderService._base_qs(restaurant, statuses, is_indoor)
        preparing = [o for o in orders if o.status == Order.Status.PREPARING and not o.special_flag]
        pending = [o for o in orders if o.status == Order.Status.PENDING and not o.special_flag]
        others = [o for o in orders if o.status not in (Order.Status.PREPARING, Order.Status.PENDING) and not o.special_flag]
        preparing = sorted(preparing, key=lambda o: o.created_at)
        pending_windowed = OrderSorter.sort_normal_with_window(pending, window_size=window_size)
        others_sorted = OrderSorter.sort_normal_with_window(others, window_size=window_size)
        return preparing + pending_windowed + others_sorted

    @staticmethod
    def get_simple_orders(restaurant):
        criteria = CriteriaService.get_or_none(restaurant)
        if criteria is None:
            return []
        orders = OrderService.get_restaurant_orders_qs(restaurant)
        return SimpleOrderDetector.detect(orders, criteria)


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
        _make_items(order, items_data)
        order.recalculate_priority_score()
        return order

    @staticmethod
    def update_order(order, validated_data):
        if order.status not in EDITABLE_ORDER_STATUSES:
            raise Conflict(
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
            raise Conflict(f'Cannot cancel an order that is already "{order.status}".')
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status', 'updated_at'])
        return order

