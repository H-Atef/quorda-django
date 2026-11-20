"""
Rebalance / reset / summary.

The same logic exists in both OrderService (used by the views) and BatchService,
so every scenario runs against both implementations to keep them in sync.
"""
from rest_framework.exceptions import ValidationError

from apps.orders.services import BatchService, OrderService
from apps.orders.tests.base import OrdersTestCase, make_order, reload

IMPLEMENTATIONS = (OrderService, BatchService)


def batches(*orders):
    return [reload(o).batch_number for o in orders]


class RebalanceTests(OrdersTestCase):

    def test_oldest_orders_from_later_batches_fill_holes(self):
        a = make_order(self.restaurant, batch_number=1, created_minutes_ago=50)
        old = make_order(self.restaurant, batch_number=2, created_minutes_ago=30)
        new = make_order(self.restaurant, batch_number=2, created_minutes_ago=10)
        for svc in IMPLEMENTATIONS:
            with self.subTest(service=svc.__name__):
                result = svc.rebalance_batches(self.restaurant, window_size=2)
                self.assertEqual(batches(a, old, new), [1, 1, 2])
                self.assertEqual(result['rebalanced'], 1)
                self.assertEqual(result['changes'][0],
                                 {'order_id': str(old.pk), 'old_batch': 2, 'new_batch': 1})
                # reset for the next implementation
                from apps.orders.models import Order
                Order.objects.filter(pk=old.pk).update(batch_number=2)

    def test_cascade_across_several_batches(self):
        b1 = make_order(self.restaurant, batch_number=1, created_minutes_ago=40)
        b2 = make_order(self.restaurant, batch_number=2, created_minutes_ago=30)
        b3 = make_order(self.restaurant, batch_number=3, created_minutes_ago=20)
        result = OrderService.rebalance_batches(self.restaurant, window_size=3)
        self.assertEqual(batches(b1, b2, b3), [1, 1, 1])
        self.assertEqual(result['rebalanced'], 2)
        self.assertEqual(result['summary_before'], [
            {'batch_number': 1, 'pending': 1}, {'batch_number': 2, 'pending': 1},
            {'batch_number': 3, 'pending': 1},
        ])
        self.assertEqual(result['summary_after'], [{'batch_number': 1, 'pending': 3}])

    def test_full_batches_are_left_alone(self):
        orders = [make_order(self.restaurant, batch_number=n) for n in (1, 1, 2, 2)]
        for svc in IMPLEMENTATIONS:
            with self.subTest(service=svc.__name__):
                self.assertEqual(svc.rebalance_batches(self.restaurant, window_size=2)['rebalanced'], 0)
        self.assertEqual(batches(*orders), [1, 1, 2, 2])

    def test_finished_orders_are_neither_moved_nor_counted(self):
        make_order(self.restaurant, batch_number=1, status='done')
        pending = make_order(self.restaurant, batch_number=2)
        done = make_order(self.restaurant, batch_number=3, status='done')
        for svc in IMPLEMENTATIONS:
            with self.subTest(service=svc.__name__):
                svc.rebalance_batches(self.restaurant, window_size=2)
        self.assertEqual(reload(done).batch_number, 3)   # audit trail untouched
        self.assertEqual(reload(pending).batch_number, 2)  # lowest active batch is already 2

    def test_target_batch_only_touches_that_batch(self):
        make_order(self.restaurant, batch_number=1)            # hole in 1
        make_order(self.restaurant, batch_number=2)            # hole in 2
        later = make_order(self.restaurant, batch_number=3, created_minutes_ago=5)
        for svc in IMPLEMENTATIONS:
            with self.subTest(service=svc.__name__):
                result = svc.rebalance_batches(self.restaurant, window_size=2, target_batch=2)
                self.assertEqual({c['new_batch'] for c in result['changes']}, {2})
                from apps.orders.models import Order
                Order.objects.filter(pk=later.pk).update(batch_number=3)

    def test_other_restaurants_are_not_touched(self):
        make_order(self.restaurant, batch_number=1)
        foreign = make_order(self.other_restaurant, batch_number=9)
        OrderService.rebalance_batches(self.restaurant, window_size=5)
        self.assertEqual(reload(foreign).batch_number, 9)

    def test_nothing_to_do_on_empty_kitchen(self):
        for svc in IMPLEMENTATIONS:
            result = svc.rebalance_batches(self.restaurant)
            self.assertEqual((result['rebalanced'], result['changes']), (0, []))


class ResetTests(OrdersTestCase):

    def setUp(self):
        self.active = make_order(self.restaurant, batch_number=4)
        self.done = make_order(self.restaurant, batch_number=3, status='done')
        self.cancelled = make_order(self.restaurant, batch_number=2, status='cancelled')

    def test_completed_mode_resets_only_finished_orders(self):
        for svc in IMPLEMENTATIONS:
            with self.subTest(service=svc.__name__):
                result = svc.reset_batches(self.restaurant, mode='completed')
                self.assertEqual(result['orders_reset'], 2)
                self.assertEqual(result['mode'], 'completed')
                self.assertEqual(result['restaurant_name'], 'A')
                self.assertEqual(batches(self.active, self.done, self.cancelled), [4, 0, 0])

    def test_all_mode_is_blocked_while_orders_are_active(self):
        for svc in IMPLEMENTATIONS:
            with self.subTest(service=svc.__name__):
                with self.assertRaises(ValidationError):
                    svc.reset_batches(self.restaurant, mode='all')
        self.assertEqual(reload(self.active).batch_number, 4)

    def test_all_mode_resets_everything_when_kitchen_is_empty(self):
        self.active.status = 'done'
        self.active.save()
        for svc in IMPLEMENTATIONS:
            with self.subTest(service=svc.__name__):
                self.assertEqual(svc.reset_batches(self.restaurant, mode='all')['orders_reset'], 3)
        self.assertEqual(batches(self.active, self.done, self.cancelled), [0, 0, 0])

    def test_unknown_mode(self):
        for svc in IMPLEMENTATIONS:
            with self.subTest(service=svc.__name__), self.assertRaises(ValidationError):
                svc.reset_batches(self.restaurant, mode='nuke')

    def test_other_restaurants_are_not_reset(self):
        foreign = make_order(self.other_restaurant, batch_number=8, status='done')
        OrderService.reset_batches(self.restaurant, mode='completed')
        self.assertEqual(reload(foreign).batch_number, 8)


class BatchSummaryTests(OrdersTestCase):

    def test_counts_active_orders_per_batch(self):
        make_order(self.restaurant, batch_number=1)
        make_order(self.restaurant, batch_number=1, status='preparing')
        make_order(self.restaurant, batch_number=1, status='done')
        make_order(self.restaurant, batch_number=2)
        self.assertEqual(OrderService._batch_summary(self.restaurant), [
            {'batch_number': 1, 'pending': 2}, {'batch_number': 2, 'pending': 1},
        ])
        self.assertEqual(
            BatchService._batch_summary(self.restaurant, ('pending', 'preparing')),
            OrderService._batch_summary(self.restaurant),
        )
