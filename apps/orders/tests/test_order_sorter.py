"""OrderSorter: batch assignment (DB) and the pure-python sort helpers."""
from datetime import datetime, timedelta, timezone as dt_tz
from types import SimpleNamespace as NS

from django.test import SimpleTestCase

from apps.orders.helpers.order_sorter import OrderSorter
from apps.orders.models import Order
from apps.orders.tests.base import OrdersTestCase, make_order


class AssignBatchNumberTests(OrdersTestCase):

    def assign(self, restaurant=None, window_size=3):
        order = Order(restaurant=restaurant or self.restaurant)
        return OrderSorter.assign_batch_number(order, window_size=window_size)

    def test_first_order_goes_to_batch_one(self):
        self.assertEqual(self.assign(), 1)

    def test_joins_newest_batch_while_it_has_room(self):
        make_order(self.restaurant, batch_number=1)
        make_order(self.restaurant, batch_number=1)
        self.assertEqual(self.assign(window_size=3), 1)

    def test_opens_new_batch_when_newest_is_full(self):
        for _ in range(3):
            make_order(self.restaurant, batch_number=1)
        self.assertEqual(self.assign(window_size=3), 2)

    def test_never_slides_back_into_an_older_batch(self):
        """Batch 1 has a hole but batch 2 exists -> new orders go to batch 2."""
        make_order(self.restaurant, batch_number=1)            # hole in batch 1
        for _ in range(3):
            make_order(self.restaurant, batch_number=2)        # full
        self.assertEqual(self.assign(window_size=3), 3)

    def test_done_and_cancelled_orders_do_not_hold_a_batch(self):
        make_order(self.restaurant, status='done', batch_number=7)
        make_order(self.restaurant, status='cancelled', batch_number=8)
        self.assertEqual(self.assign(), 1)  # kitchen is empty -> restart

    def test_preparing_orders_count_as_active(self):
        make_order(self.restaurant, status='preparing', batch_number=4)
        self.assertEqual(self.assign(window_size=3), 4)

    def test_restaurants_are_isolated(self):
        for _ in range(3):
            make_order(self.other_restaurant, batch_number=5)
        self.assertEqual(self.assign(), 1)

    def test_assignment_is_in_memory_only(self):
        order = Order(restaurant=self.restaurant)
        OrderSorter.assign_batch_number(order)
        self.assertEqual(order.batch_number, 1)
        self.assertEqual(Order.objects.count(), 0)  # caller is responsible for saving


class SortHelpersTests(SimpleTestCase):
    """Pure python, no database."""
    T0 = datetime(2026, 1, 1, tzinfo=dt_tz.utc)

    def order(self, name, *, vip=False, score=0.0, minutes=0, batch=1, restaurant=1):
        return NS(name=name, special_flag=vip, priority_score=score,
                  created_at=self.T0 + timedelta(minutes=minutes),
                  batch_number=batch, restaurant_id=restaurant)

    def names(self, orders):
        return [o.name for o in orders]

    def test_vip_before_normal_inside_a_batch(self):
        orders = [self.order('normal', score=0.9), self.order('vip', vip=True, score=0.1)]
        self.assertEqual(self.names(OrderSorter.sort_with_batches(orders)), ['vip', 'normal'])

    def test_vips_are_oldest_first(self):
        orders = [self.order('late', vip=True, minutes=5), self.order('early', vip=True, minutes=1)]
        self.assertEqual(self.names(OrderSorter.sort_with_batches(orders)), ['early', 'late'])

    def test_normals_highest_score_first_then_oldest(self):
        orders = [
            self.order('low', score=0.2),
            self.order('high_late', score=0.8, minutes=9),
            self.order('high_early', score=0.8, minutes=1),
        ]
        self.assertEqual(self.names(OrderSorter.sort_with_batches(orders)),
                         ['high_early', 'high_late', 'low'])

    def test_batch_beats_score_and_vip(self):
        """Starvation protection: an old batch is served before a newer VIP."""
        orders = [
            self.order('new_vip', vip=True, batch=2),
            self.order('old_low', score=0.01, batch=1),
        ]
        self.assertEqual(self.names(OrderSorter.sort_with_batches(orders)), ['old_low', 'new_vip'])

    def test_get_vip_and_normal_split(self):
        orders = [self.order('n1', score=0.3), self.order('v1', vip=True, minutes=2),
                  self.order('n2', score=0.7), self.order('v0', vip=True, minutes=1)]
        self.assertEqual(self.names(OrderSorter.get_vip_orders(orders)), ['v0', 'v1'])
        self.assertEqual(self.names(OrderSorter.get_normal_orders(orders)), ['n2', 'n1'])

    def test_empty_input(self):
        self.assertEqual(OrderSorter.sort_with_batches([]), [])
