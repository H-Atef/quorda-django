"""OrderService: create / update / cancel, listing & sorting, simple orders, claim."""
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import ValidationError

from apps.orders.models import Order, OrderItem
from apps.orders.services import OrderService
from apps.orders.tests.base import (
    OrdersTestCase, create_cashier, create_customer, make_order, reload,
)
from apps.restaurants.models import Criteria


def items_payload(*pairs):
    """[(menu_item, qty), ...] -> the validated_data shape the serializer produces."""
    return [{'menu_item': m, 'quantity': q} for m, q in pairs]


class CreateOrderTests(OrdersTestCase):

    def create(self, actor=None, window_size=10, **data):
        data.setdefault('order_items', items_payload((self.fries, 2)))
        return OrderService.create_order(
            self.restaurant, data, actor=actor or self.owner, window_size=window_size,
        )

    def test_creates_dine_in_order_with_items_and_audit_fields(self):
        order = self.create()
        self.assertTrue(order.is_indoor)
        self.assertEqual(order.created_by, self.owner)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.order_items.count(), 1)

    def test_snapshots_unit_price(self):
        order = self.create()
        self.assertEqual(order.order_items.get().unit_price, Decimal('2.00'))

    def test_computes_priority_score(self):
        # 2x fries: time 2 min -> 2/3 ; qty 2 -> 2/3 ; priority 5 -> 1
        self.assertAlmostEqual(self.create().priority_score, 0.4 * (2 / 3) + 0.4 * (2 / 3) + 0.2)

    def test_first_order_is_batch_one(self):
        self.assertEqual(self.create().batch_number, 1)

    def test_new_batch_opens_when_window_is_full(self):
        batches = [self.create(window_size=2).batch_number for _ in range(5)]
        self.assertEqual(batches, [1, 1, 2, 2, 3])

    def test_client_cannot_inject_protected_fields(self):
        order = self.create(is_indoor=False, customer=create_customer(), created_by=None, shift=None)
        self.assertTrue(order.is_indoor)
        self.assertIsNone(order.customer)
        self.assertEqual(order.created_by, self.owner)

    def test_owner_may_create_vip(self):
        self.assertTrue(self.create(special_flag=True).special_flag)

    def test_cashier_without_permission_cannot_create_vip(self):
        cashier = create_cashier(self.restaurant, can_set_vip=False)
        with self.assertRaises(ValidationError):
            self.create(actor=cashier, special_flag=True)
        self.assertEqual(Order.objects.count(), 0)

    def test_cashier_with_permission_can_create_vip(self):
        cashier = create_cashier(self.restaurant, can_set_vip=True)
        self.assertTrue(self.create(actor=cashier, special_flag=True).special_flag)

    def test_deactivated_cashier_loses_vip_permission(self):
        cashier = create_cashier(self.restaurant, can_set_vip=True, is_active=False)
        with self.assertRaises(ValidationError):
            self.create(actor=cashier, special_flag=True)

    def test_cashier_can_create_normal_order_without_permission(self):
        cashier = create_cashier(self.restaurant)
        order = self.create(actor=cashier)
        self.assertEqual(order.created_by, cashier)


class UpdateOrderTests(OrdersTestCase):

    def setUp(self):
        self.order = OrderService.create_order(
            self.restaurant, {'order_items': items_payload((self.fries, 1))}, actor=self.owner,
        )

    def test_status_change(self):
        OrderService.update_order(self.order, {'status': 'done'}, actor=self.owner)
        self.assertEqual(reload(self.order).status, 'done')

    def test_replacing_items_recomputes_score(self):
        before = reload(self.order).priority_score
        OrderService.update_order(
            self.order, {'order_items': items_payload((self.steak, 5))}, actor=self.owner,
        )
        after = reload(self.order)
        self.assertEqual(list(after.order_items.values_list('menu_item__name', flat=True)), ['Steak'])
        self.assertLess(after.priority_score, before)

    def test_omitting_items_keeps_them(self):
        OrderService.update_order(self.order, {'status': 'done'}, actor=self.owner)
        self.assertEqual(reload(self.order).order_items.count(), 1)

    def test_protected_fields_are_ignored(self):
        batch = self.order.batch_number
        OrderService.update_order(
            self.order,
            {'batch_number': 99, 'is_indoor': False, 'customer': create_customer(), 'status': 'done'},
            actor=self.owner,
        )
        fresh = reload(self.order)
        self.assertEqual(fresh.batch_number, batch)
        self.assertTrue(fresh.is_indoor)
        self.assertIsNone(fresh.customer)

    def test_finished_orders_cannot_be_modified(self):
        for status in ('done', 'cancelled'):
            with self.subTest(status=status):
                order = make_order(self.restaurant, [(self.fries, 1)], status=status)
                with self.assertRaises(ValidationError):
                    OrderService.update_order(order, {'status': 'pending'}, actor=self.owner)
                self.assertEqual(reload(order).status, status)

    def test_cashier_cannot_toggle_vip_without_permission(self):
        cashier = create_cashier(self.restaurant)
        with self.assertRaises(ValidationError):
            OrderService.update_order(self.order, {'special_flag': True}, actor=cashier)

    def test_resending_same_vip_value_is_not_a_change(self):
        cashier = create_cashier(self.restaurant)
        OrderService.update_order(self.order, {'special_flag': False}, actor=cashier)  # no error

    def test_cashier_with_permission_can_toggle_vip(self):
        cashier = create_cashier(self.restaurant, can_set_vip=True)
        OrderService.update_order(self.order, {'special_flag': True}, actor=cashier)
        self.assertTrue(reload(self.order).special_flag)


class CancelAndDeleteTests(OrdersTestCase):

    def test_cancel_active_orders(self):
        for status in ('pending',):
            with self.subTest(status=status):
                order = make_order(self.restaurant, [(self.fries, 1)], status=status)
                OrderService.cancel_order(order)
                self.assertEqual(reload(order).status, 'cancelled')

    def test_cannot_cancel_finished_orders(self):
        for status in ('done', 'cancelled'):
            with self.subTest(status=status):
                order = make_order(self.restaurant, [(self.fries, 1)], status=status)
                with self.assertRaises(ValidationError):
                    OrderService.cancel_order(order)

    def test_delete_removes_order_and_items(self):
        order = make_order(self.restaurant, [(self.fries, 1)])
        OrderService.delete_order(order)
        self.assertFalse(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(OrderItem.objects.count(), 0)


class OrderOwnershipTests(OrdersTestCase):

    def test_get_owned_order(self):
        order = make_order(self.restaurant)
        self.assertEqual(OrderService.get_owned_order(self.restaurant, order.pk), order)

    def test_other_restaurants_order_is_404(self):
        from django.http import Http404
        order = make_order(self.other_restaurant)
        with self.assertRaises(Http404):
            OrderService.get_owned_order(self.restaurant, order.pk)

    def test_get_owned_item_checks_order_membership(self):
        from django.http import Http404
        order_a = make_order(self.restaurant, [(self.fries, 1)])
        order_b = make_order(self.restaurant, [(self.burger, 1)])
        item_of_b = order_b.order_items.get()
        with self.assertRaises(Http404):
            OrderService.get_owned_item(self.restaurant, order_a.pk, item_of_b.pk)


class ListOrdersTests(OrdersTestCase):
    """The universal read method behind every kitchen endpoint."""

    def ids(self, **kwargs):
        return [o.pk for o in OrderService.list_orders(self.restaurant, **kwargs)]

    def test_defaults_to_active_orders_only(self):
        active = make_order(self.restaurant, status='pending', batch_number=1)
        active2 = make_order(self.restaurant, status='pending', batch_number=1)
        make_order(self.restaurant, status='done', batch_number=1)
        make_order(self.restaurant, status='cancelled', batch_number=1)
        self.assertCountEqual(self.ids(), [active.pk, active2.pk])

    def test_explicit_statuses(self):
        done = make_order(self.restaurant, status='done', batch_number=1)
        make_order(self.restaurant, status='pending', batch_number=1)
        self.assertEqual(self.ids(statuses=['done']), [done.pk])

    def test_only_this_restaurants_orders(self):
        mine = make_order(self.restaurant, batch_number=1)
        make_order(self.other_restaurant, batch_number=1)
        self.assertEqual(self.ids(), [mine.pk])

    def test_vip_filter(self):
        vip = make_order(self.restaurant, special_flag=True, batch_number=1)
        normal = make_order(self.restaurant, batch_number=1)
        self.assertEqual(self.ids(vip_only=True), [vip.pk])
        self.assertEqual(self.ids(vip_only=False), [normal.pk])
        self.assertCountEqual(self.ids(vip_only=None), [vip.pk, normal.pk])

    def test_channel_filter(self):
        indoor = make_order(self.restaurant, is_indoor=True, batch_number=1)
        delivery = make_order(self.restaurant, is_indoor=False, customer=create_customer(), batch_number=1)
        self.assertEqual(self.ids(is_indoor=True), [indoor.pk])
        self.assertEqual(self.ids(is_indoor=False), [delivery.pk])

    def test_windowed_order_batch_then_vip_then_score_then_age(self):
        b2_vip = make_order(self.restaurant, special_flag=True, batch_number=2, score=0.1)
        b1_low = make_order(self.restaurant, batch_number=1, score=0.2)
        b1_high = make_order(self.restaurant, batch_number=1, score=0.9)
        b1_vip = make_order(self.restaurant, special_flag=True, batch_number=1, score=0.0)
        self.assertEqual(self.ids(), [b1_vip.pk, b1_high.pk, b1_low.pk, b2_vip.pk])

    def test_equal_scores_fall_back_to_oldest_first(self):
        newer = make_order(self.restaurant, batch_number=1, score=0.5, created_minutes_ago=1)
        older = make_order(self.restaurant, batch_number=1, score=0.5, created_minutes_ago=9)
        self.assertEqual(self.ids(), [older.pk, newer.pk])

    def test_pure_vip_listing_is_oldest_first(self):
        newer = make_order(self.restaurant, special_flag=True, batch_number=1, created_minutes_ago=1)
        older = make_order(self.restaurant, special_flag=True, batch_number=1, created_minutes_ago=9)
        self.assertEqual(self.ids(vip_only=True), [older.pk, newer.pk])

    def test_unwindowed_ignores_batches(self):
        """Pure priority order: a high score in a later batch beats an earlier batch."""
        early_batch = make_order(self.restaurant, batch_number=1, score=0.1)
        late_batch = make_order(self.restaurant, batch_number=5, score=0.9)
        self.assertEqual(self.ids(windowed=False), [late_batch.pk, early_batch.pk])

    def test_limit(self):
        for i in range(4):
            make_order(self.restaurant, batch_number=1, score=i / 10)
        self.assertEqual(len(self.ids(limit=3)), 3)

    def test_batch_limit_keeps_the_first_n_batches(self):
        b1 = make_order(self.restaurant, batch_number=1)
        b2 = make_order(self.restaurant, batch_number=2)
        make_order(self.restaurant, batch_number=3)
        self.assertCountEqual(self.ids(batch_limit=2), [b1.pk, b2.pk])

    def test_ordering_override(self):
        old = make_order(self.restaurant, batch_number=1, created_minutes_ago=30, score=0.9)
        new = make_order(self.restaurant, batch_number=1, created_minutes_ago=1, score=0.1)
        self.assertEqual(self.ids(ordering='-created_at'), [new.pk, old.pk])
        self.assertEqual(self.ids(ordering='priority_score,  created_at'), [new.pk, old.pk])

    def test_query_count_does_not_grow_with_order_count(self):
        """Guard against N+1: items, menu items and categories are prefetched."""
        def run():
            with CaptureQueriesContext(connection) as ctx:
                for o in OrderService.list_orders(self.restaurant):
                    list(o.order_items.all())
                    for i in o.order_items.all():
                        i.menu_item.category
            return len(ctx)

        make_order(self.restaurant, [(self.fries, 1)], batch_number=1)
        small = run()
        for _ in range(8):
            make_order(self.restaurant, [(self.fries, 1), (self.steak, 2)], batch_number=1)
        self.assertEqual(run(), small)

    def test_convenience_wrappers(self):
        vip = make_order(self.restaurant, special_flag=True, batch_number=1)
        indoor = make_order(self.restaurant, batch_number=1)
        outdoor = make_order(self.restaurant, is_indoor=False, customer=create_customer(), batch_number=1)
        names = lambda orders: [o.pk for o in orders]  # noqa: E731
        self.assertEqual(names(OrderService.get_vip_orders(self.restaurant)), [vip.pk])
        self.assertEqual(names(OrderService.get_indoor_normal_windowed(self.restaurant)), [indoor.pk])
        self.assertEqual(names(OrderService.get_outdoor_normal_windowed(self.restaurant)), [outdoor.pk])
        self.assertCountEqual(
            names(OrderService.get_windowed_orders(self.restaurant, window_size=999)),
            [vip.pk, indoor.pk, outdoor.pk],
        )
        self.assertCountEqual(
            names(OrderService.get_normal_windowed_orders(self.restaurant)), [indoor.pk, outdoor.pk],
        )


class SimpleOrdersTests(OrdersTestCase):
    """simple = total qty <= max_quantity AND best category priority >= min priority."""

    def setUp(self):
        Criteria.objects.create(restaurant=self.restaurant, max_quantity=2, min_category_priority=3)

    def simple_ids(self):
        return [o.pk for o in OrderService.get_simple_orders(self.restaurant)]

    def test_no_criteria_means_no_simple_orders(self):
        Criteria.objects.all().delete()
        self.restaurant = type(self.restaurant).objects.get(pk=self.restaurant.pk)  # drop cached relation
        make_order(self.restaurant, [(self.fries, 1)])
        self.assertEqual(self.simple_ids(), [])

    def test_matching_order(self):
        order = make_order(self.restaurant, [(self.fries, 2)])
        self.assertEqual(self.simple_ids(), [order.pk])

    def test_too_many_items(self):
        make_order(self.restaurant, [(self.fries, 3)])
        self.assertEqual(self.simple_ids(), [])

    def test_category_priority_too_low(self):
        make_order(self.restaurant, [(self.steak, 1)])
        self.assertEqual(self.simple_ids(), [])

    def test_vip_and_finished_orders_are_excluded(self):
        make_order(self.restaurant, [(self.fries, 1)], special_flag=True)
        make_order(self.restaurant, [(self.fries, 1)], status='done')
        self.assertEqual(self.simple_ids(), [])

    def test_oldest_first(self):
        new = make_order(self.restaurant, [(self.fries, 1)], created_minutes_ago=1)
        old = make_order(self.restaurant, [(self.fries, 1)], created_minutes_ago=9)
        self.assertEqual(self.simple_ids(), [old.pk, new.pk])

    def test_other_restaurants_are_excluded(self):
        Criteria.objects.create(restaurant=self.other_restaurant, max_quantity=9, min_category_priority=1)
        make_order(self.other_restaurant, [(self.other_menu['fries'], 1)])
        self.assertEqual(self.simple_ids(), [])


class ClaimOrderTests(OrdersTestCase):

    def test_claim_returns_pending_order(self):
        order = make_order(self.restaurant, [(self.fries, 1)])
        claimed = OrderService.claim_order(self.restaurant, order.pk, self.owner)
        self.assertEqual(claimed.status, 'pending')
        self.assertEqual(reload(order).status, 'pending')

    def test_second_claim_succeeds(self):
        order = make_order(self.restaurant, [(self.fries, 1)])
        OrderService.claim_order(self.restaurant, order.pk, self.owner)
        claimed = OrderService.claim_order(self.restaurant, order.pk, self.owner)
        self.assertEqual(claimed.status, 'pending')

    def test_only_pending_orders_can_be_claimed(self):
        for status in ('done', 'cancelled'):
            with self.subTest(status=status):
                order = make_order(self.restaurant, status=status)
                with self.assertRaises(ValidationError):
                    OrderService.claim_order(self.restaurant, order.pk, self.owner)

    def test_cannot_claim_another_restaurants_order(self):
        order = make_order(self.other_restaurant)
        with self.assertRaises(ValidationError):
            OrderService.claim_order(self.restaurant, order.pk, self.owner)
        self.assertEqual(reload(order).status, 'pending')
