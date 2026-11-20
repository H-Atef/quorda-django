from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from apps.orders.helpers.order_sorter import OrderSorter, ACTIVE_STATUSES
from apps.orders.helpers.simple_order_detector import SimpleOrderDetector
from apps.orders.models import Order, OrderItem
from apps.restaurants.services import CriteriaService
from apps.users.helpers.constants import UserRole
from apps.users.models import RestaurantProfile


EDITABLE_ORDER_STATUSES = (Order.Status.PENDING,)


def _assert_can_set_vip(actor, current_flag, requested_flag):
    if requested_flag == current_flag:
        return
    if actor.role == UserRole.RESTAURANT:
        return
    if actor.role == UserRole.CASHIER:
        profile = getattr(actor, 'cashier_profile', None)
        if profile and profile.is_active and profile.can_set_vip:
            return
    raise ValidationError('You do not have permission to change the VIP flag.')


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

    # ================================================================
    # Base querysets
    # ================================================================

    @staticmethod
    def _base_qs(restaurant):
        return (
            Order.objects.filter(restaurant=restaurant)
            .select_related('created_by', 'shift')
            .prefetch_related('order_items__menu_item__category')
        )

    @staticmethod
    def get_restaurant_orders_qs(restaurant):
        return OrderService._base_qs(restaurant)

    @staticmethod
    def get_owned_order(restaurant, order_pk):
        return get_object_or_404(
            Order.objects
            .select_related('created_by', 'shift')
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

    # ================================================================
    # CRUD — atomic, batch-aware
    # ================================================================

    @staticmethod
    @transaction.atomic
    def create_order(restaurant, validated_data, actor, window_size=10):
        """Create order + assign batch_number + create items — all-or-nothing."""
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
        OrderSorter.assign_batch_number(order, window_size=window_size)
        order.save(update_fields=['batch_number'])

        _make_items(order, items_data)
        order.recalculate_priority_score()
        return order

    @staticmethod
    def _assert_editable(order):
        if order.status not in EDITABLE_ORDER_STATUSES:
            raise ValidationError(
                f'Cannot modify an order that is "{order.status}". '
                f'Only pending orders can be modified.'
            )

    @staticmethod
    @transaction.atomic
    def update_order(order, validated_data, actor):
        OrderService._assert_editable(order)
        items_data = validated_data.pop('order_items', None)
        if 'special_flag' in validated_data:
            _assert_can_set_vip(
                actor, order.special_flag, bool(validated_data['special_flag']),
            )
        for attr, value in validated_data.items():
            if attr in ('is_indoor', 'customer', 'created_by', 'shift', 'restaurant', 'batch_number'):
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
        """Delete — holes left in batch are filled only by rebalance."""
        order.delete()

    @staticmethod
    def cancel_order(order, actor=None):
        if order.status in (Order.Status.DONE, Order.Status.CANCELLED):
            raise ValidationError(f'Cannot cancel an order that is already "{order.status}".')
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

    # ================================================================
    # Universal list endpoint — the primary read method
    # ================================================================

    @staticmethod
    def list_orders(
        restaurant,
        *,
        vip_only=None,           # None = all; True = VIPs; False = non-VIP
        is_indoor=None,          # None = both; True = dine-in; False = delivery
        statuses=None,           # None = [PENDING]
        windowed=True,           # True = batch-sorted; False = priority-only
        limit=None,
        batch_limit=None,        # Max number of batches to return (by batch_number ASC)
        ordering=None,           # Optional ordering override, e.g. '-created_at'
    ):
        """
        Universal filter + sort.

        Windowed sort (default):
            batch_number ASC, VIPs first, then -priority_score, then created_at.
            Legacy orders (batch_number=0) appear first (they're oldest).

        Unwindowed sort:
            -priority_score DESC, created_at ASC  (pure priority — can starve).

        batch_limit: restrict results to the first N batches (ordered by batch_number ASC).
        ordering: optional override ordering, e.g. '-created_at' or 'priority_score'.
        """
        qs = OrderService._base_qs(restaurant)

        if statuses is None:
            statuses = list(ACTIVE_STATUSES)
        qs = qs.filter(status__in=statuses)

        if vip_only is True:
            qs = qs.filter(special_flag=True)
        elif vip_only is False:
            qs = qs.filter(special_flag=False)

        if is_indoor is not None:
            qs = qs.filter(is_indoor=is_indoor)

        if batch_limit is not None:
            batch_nums = (
                Order.objects
                .filter(restaurant=restaurant, status__in=statuses)
                .values_list('batch_number', flat=True)
                .distinct()
                .order_by('batch_number')[:batch_limit]
            )
            qs = qs.filter(batch_number__in=batch_nums)

        if ordering:
            qs = qs.order_by(*[f.strip() for f in ordering.split(',') if f.strip()])
        elif windowed:
            if vip_only is True:
                # Pure VIP: oldest-first within batch
                qs = qs.order_by('batch_number', 'created_at')
            elif vip_only is False:
                # Pure normal: score desc within batch
                qs = qs.order_by('batch_number', '-priority_score', 'created_at')
            else:
                # Mixed: VIPs first within batch, then normals by score.
                # (-special_flag: True(1) > False(0) descending → VIPs first)
                qs = qs.order_by(
                    'batch_number', '-special_flag', '-priority_score', 'created_at',
                )
        else:
            # Unwindowed: priority sort (NOT chronological — matches legacy behavior)
            qs = qs.order_by('-special_flag', '-priority_score', 'created_at')

        return list(qs[:limit]) if limit else list(qs)

    # ================================================================
    # Convenience wrappers
    # ================================================================

    @staticmethod
    def get_vip_orders(restaurant):
        return OrderService.list_orders(restaurant, vip_only=True, windowed=True)

    @staticmethod
    def get_indoor_normal_windowed(restaurant):
        return OrderService.list_orders(restaurant, vip_only=False, is_indoor=True, windowed=True)

    @staticmethod
    def get_outdoor_normal_windowed(restaurant):
        return OrderService.list_orders(restaurant, vip_only=False, is_indoor=False, windowed=True)

    @staticmethod
    def get_windowed_orders(restaurant, window_size=None, statuses=None, is_indoor=None):
        """Legacy compat. window_size ignored (batch_number handles sizing)."""
        return OrderService.list_orders(
            restaurant, vip_only=None, statuses=statuses, is_indoor=is_indoor, windowed=True,
        )

    @staticmethod
    def get_normal_windowed_orders(restaurant, window_size=None, statuses=None, is_indoor=None):
        """Legacy compat."""
        return OrderService.list_orders(
            restaurant, vip_only=False, statuses=statuses, is_indoor=is_indoor, windowed=True,
        )

    @staticmethod
    def get_simple_orders(restaurant):
        """Simple orders: active, non-VIP, passing SimpleOrderDetector."""
        criteria = CriteriaService.get_or_none(restaurant)
        if criteria is None:
            return []
        qs = (
            OrderService._base_qs(restaurant)
            .filter(status__in=ACTIVE_STATUSES, special_flag=False)
        )
        return list(SimpleOrderDetector.detect(qs, criteria).order_by('created_at'))

    # ================================================================
    # Rebalance — fill holes by promoting oldest from later batches
    # ================================================================

    @classmethod
    @transaction.atomic
    def rebalance_batches(cls, restaurant, window_size=10, target_batch=None):
        """
        Promote oldest pending from later batches into holes in earlier batches.

        Cascade: filling batch 1 creates a hole in batch 2 → batch 2 fills
        from batch 3, etc. Only ACTIVE orders are moved. Promotions are
        always oldest-first (by created_at).

        Returns:
            {'rebalanced': N, 'changes': [...], 'summary_before': [...], 'summary_after': [...]}
        """
        RestaurantProfile.objects.select_for_update().get(pk=restaurant.pk)

        summary_before = cls._batch_summary(restaurant)
        changes = []

        if target_batch is not None:
            batches = [target_batch]
        else:
            batches = list(
                Order.objects
                .filter(restaurant=restaurant, status__in=ACTIVE_STATUSES)
                .values_list('batch_number', flat=True)
                .distinct()
                .order_by('batch_number')
            )

        for batch_num in batches:
            pending_here = Order.objects.filter(
                restaurant=restaurant,
                batch_number=batch_num,
                status__in=ACTIVE_STATUSES,
            ).count()

            holes = window_size - pending_here
            if holes <= 0:
                continue

            promote = list(
                Order.objects
                .filter(
                    restaurant=restaurant,
                    batch_number__gt=batch_num,
                    status__in=ACTIVE_STATUSES,
                )
                .order_by('batch_number', 'created_at')[:holes]
            )
            if not promote:
                continue

            old_batches = {o.pk: o.batch_number for o in promote}
            Order.objects.filter(pk__in=old_batches.keys()).update(batch_number=batch_num)

            for o in promote:
                changes.append({
                    'order_id': str(o.pk),
                    'old_batch': old_batches[o.pk],
                    'new_batch': batch_num,
                })

        return {
            'rebalanced': len(changes),
            'changes': changes,
            'summary_before': summary_before,
            'summary_after': cls._batch_summary(restaurant),
        }

    @staticmethod
    def _batch_summary(restaurant):
        from django.db.models import Count
        return list(
            Order.objects
            .filter(restaurant=restaurant, status__in=ACTIVE_STATUSES)
            .values('batch_number')
            .annotate(pending=Count('id'))
            .order_by('batch_number')
        )

    # ================================================================
    # Reset batches
    # ================================================================

    @classmethod
    @transaction.atomic
    def reset_batches(cls, restaurant, mode='completed'):
        """
        Reset batch_number to 0 for this restaurant.

        mode='completed' (default, safe):
            Reset only DONE/CANCELLED orders. Pending orders keep their batches.

        mode='all' (dangerous):
            Reset EVERY order. Blocked if any pending order exists.
            Use at shift start when the kitchen is empty.

        Returns:
            {'mode', 'restaurant_id', 'restaurant_name', 'orders_reset'}
        """
        RestaurantProfile.objects.select_for_update().get(pk=restaurant.pk)

        if mode == 'all':
            active = Order.objects.filter(
                restaurant=restaurant, status__in=ACTIVE_STATUSES,
            ).count()
            if active > 0:
                raise ValidationError({
                    'mode': (
                        f'Cannot reset all batches: {active} pending '
                        f'orders exist. Complete or cancel them first, or use '
                        f'mode=completed.'
                    )
                })
            qs = Order.objects.filter(restaurant=restaurant)
        elif mode == 'completed':
            qs = Order.objects.filter(
                restaurant=restaurant,
                status__in=[Order.Status.DONE, Order.Status.CANCELLED],
            )
        else:
            raise ValidationError({'mode': "Must be 'completed' or 'all'."})

        count = qs.update(batch_number=0)
        return {
            'mode': mode,
            'restaurant_id': str(restaurant.pk),
            'restaurant_name': restaurant.restaurant_name,
            'orders_reset': count,
        }

    # ================================================================
    # Claim — for staff starting to cook (atomic)
    # ================================================================

    @staticmethod
    @transaction.atomic
    def claim_order(restaurant, order_id, worker):
        """
        Claim a pending order for cooking. Race-safe via
        select_for_update(skip_locked=True). Scoped to restaurant.
        """
        order = (
            Order.objects
            .select_for_update(skip_locked=True)
            .filter(
                pk=order_id,
                restaurant=restaurant,
                status=Order.Status.PENDING,
            )
            .first()
        )
        if order is None:
            raise ValidationError({'order': 'Already claimed or not pending.'})
        return order


# ============================================================
# Customer-facing (delivery) service
# ============================================================

class CustomerOrderService:

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
            Order.objects
            .select_related('created_by', 'shift')
            .prefetch_related('order_items__menu_item__category'),
            pk=order_pk,
            customer=customer,
            is_indoor=False,
        )

    @staticmethod
    @transaction.atomic
    def create_order(customer, restaurant, validated_data, window_size=10):
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
        OrderSorter.assign_batch_number(order, window_size=window_size)
        order.save(update_fields=['batch_number'])

        _make_items(order, items_data)
        order.recalculate_priority_score()
        return order

    @staticmethod
    @transaction.atomic
    def update_order(order, validated_data):
        if order.status not in EDITABLE_ORDER_STATUSES:
            raise ValidationError(f'Cannot modify an order that is already "{order.status}".')
        items_data = validated_data.pop('order_items', None)
        for attr, value in validated_data.items():
            if attr == 'batch_number':
                continue
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