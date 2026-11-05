from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from apps.orders.models import Order, OrderItem
from apps.orders.helpers.order_sorter import OrderSorter
from apps.orders.helpers.simple_order_detector import SimpleOrderDetector
from apps.restaurants.services import CriteriaService

ACTIVE_ORDER_STATUSES = (Order.Status.PENDING, Order.Status.PREPARING)


class OrderService:
    """Business logic for restaurant-owner order operations (dine-in +
    management of all orders belonging to the restaurant)."""

    # ---- querysets / lookups -------------------------------------------------

    @staticmethod
    def get_restaurant_orders_qs(restaurant):
        return (
            Order.objects.filter(restaurant=restaurant)
            .prefetch_related('order_items__menu_item__category')
        )

    @staticmethod
    def get_owned_order(restaurant, order_pk):
        """Fetch an order and enforce that it belongs to `restaurant`.
        Raises Http404 (not DoesNotExist) so it doesn't need to be caught
        by the view, and doesn't distinguish "missing" from "not yours"."""
        return get_object_or_404(
            Order.objects.prefetch_related('order_items__menu_item__category'),
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

    # ---- order CRUD ------------------------------------------------------

    @staticmethod
    def create_order(restaurant, validated_data):
        items_data = validated_data.pop('order_items')
        order = Order.objects.create(restaurant=restaurant, **validated_data)
        OrderItem.objects.bulk_create([
            OrderItem(order=order, **item) for item in items_data
        ])
        order.recalculate_priority_score()
        return order

    @staticmethod
    def update_order(order, validated_data):
        items_data = validated_data.pop('order_items', None)
        for attr, value in validated_data.items():
            setattr(order, attr, value)
        order.save()

        if items_data is not None:
            order.order_items.all().delete()
            OrderItem.objects.bulk_create([
                OrderItem(order=order, **item) for item in items_data
            ])
            order.recalculate_priority_score()

        return order

    @staticmethod
    def delete_order(order):
        order.delete()

    # ---- order item CRUD --------------------------------------------------
    # Item CRUD via services/views must explicitly recalculate because the
    # service layer mutates items directly and bulk operations do not run
    # model-level hooks.

    @staticmethod
    def add_item(order, validated_data):
        item = OrderItem.objects.create(order=order, **validated_data)
        order.recalculate_priority_score()
        return item

    @staticmethod
    def update_item(item, validated_data):
        for attr, value in validated_data.items():
            setattr(item, attr, value)
        item.save()
        item.order.recalculate_priority_score()
        return item

    @staticmethod
    def delete_item(item):
        order = item.order
        item.delete()
        order.recalculate_priority_score()

    # ---- listing / analytics helpers --------------------------------------

    @staticmethod
    def get_vip_orders(restaurant):
        orders = OrderService.get_restaurant_orders_qs(restaurant)
        return OrderSorter.get_vip_orders(orders)

    @staticmethod
    def get_windowed_orders(restaurant, window_size, statuses=None):
        orders = OrderService.get_restaurant_orders_qs(restaurant)
        if statuses is None:
            statuses = ACTIVE_ORDER_STATUSES
        orders = list(orders.filter(status__in=statuses))
        preparing = [o for o in orders if o.status == Order.Status.PREPARING]
        pending = [o for o in orders if o.status == Order.Status.PENDING]
        others = [o for o in orders if o.status not in (Order.Status.PREPARING, Order.Status.PENDING)]
        preparing = sorted(preparing, key=lambda o: o.created_at)
        pending_windowed = OrderSorter.sort_with_window(pending, window_size=window_size)
        others_sorted = OrderSorter.sort_with_window(others, window_size=window_size)
        return preparing + pending_windowed + others_sorted

    @staticmethod
    def get_normal_windowed_orders(restaurant, window_size, statuses=None):
        orders = OrderService.get_restaurant_orders_qs(restaurant)
        if statuses is None:
            statuses = ACTIVE_ORDER_STATUSES
        orders = list(orders.filter(status__in=statuses))
        preparing = [o for o in orders if o.status == Order.Status.PREPARING and not o.special_flag]
        pending = [o for o in orders if o.status == Order.Status.PENDING and not o.special_flag]
        others = [o for o in orders if o.status not in (Order.Status.PREPARING, Order.Status.PENDING) and not o.special_flag]
        preparing = sorted(preparing, key=lambda o: o.created_at)
        pending_windowed = OrderSorter.sort_normal_with_window(pending, window_size=window_size)
        others_sorted = OrderSorter.sort_normal_with_window(others, window_size=window_size)
        return preparing + pending_windowed + others_sorted

    @staticmethod
    def get_simple_orders(restaurant):
        """Return orders matching the restaurant's simple-order criteria.

        An order is "simple" when its total quantity is <= the restaurant's
        ``Criteria.max_quantity`` AND the highest category priority among its
        items is >= the restaurant's ``Criteria.min_category_priority``.

        Falls back to an empty list when no criteria are configured for the
        restaurant (simple-order detection is undefined without criteria).
        """
        criteria = CriteriaService.get_or_none(restaurant)
        if criteria is None:
            return []
        orders = OrderService.get_restaurant_orders_qs(restaurant)
        return SimpleOrderDetector.detect(orders, criteria)


class CustomerOrderService:
    """Business logic for customer-facing delivery orders (is_indoor=False).

    A customer may only ever see/touch orders where `customer == user` and
    `is_indoor == False`. Modification is only allowed while the order is
    still PENDING; cancellation is allowed any time before it's DONE or
    already CANCELLED.
    """

    # ---- querysets / lookups -----------------------------------------------

    @staticmethod
    def get_customer_orders_qs(customer):
        return (
            Order.objects.filter(customer=customer, is_indoor=False)
            .prefetch_related('order_items__menu_item__category')
        )

    @staticmethod
    def get_owned_order(customer, order_pk):
        return get_object_or_404(
            Order.objects.prefetch_related('order_items__menu_item__category'),
            pk=order_pk,
            customer=customer,
            is_indoor=False,
        )

    # ---- order CRUD ------------------------------------------------------

    @staticmethod
    def create_order(customer, restaurant, validated_data):
        items_data = validated_data.pop('order_items')
        order = Order.objects.create(
            restaurant=restaurant,
            customer=customer,
            is_indoor=False,
            **validated_data,
        )
        OrderItem.objects.bulk_create([
            OrderItem(order=order, **item) for item in items_data
        ])
        order.recalculate_priority_score()
        return order

    @staticmethod
    def update_order(order, validated_data):
        if order.status != Order.Status.PENDING:
            raise ValidationError(
                f'Cannot modify an order that is already "{order.status}". '
                'Only pending orders can be modified.'
            )

        items_data = validated_data.pop('order_items', None)
        for attr, value in validated_data.items():
            setattr(order, attr, value)
        order.save()

        if items_data is not None:
            order.order_items.all().delete()
            OrderItem.objects.bulk_create([
                OrderItem(order=order, **item) for item in items_data
            ])
            order.recalculate_priority_score()

        return order

    @staticmethod
    def cancel_order(order):
        if order.status in (Order.Status.DONE, Order.Status.CANCELLED):
            raise ValidationError(
                f'Cannot cancel an order that is already "{order.status}".'
            )
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status', 'updated_at'])
        return order