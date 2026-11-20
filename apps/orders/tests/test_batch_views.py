"""Batch management endpoints: summary, rebalance, reset."""
from apps.orders.tests.base import OrdersAPITestCase, create_cashier, create_customer, make_order, reload

SUMMARY = '/api/v1/orders/batch/summary/'
REBALANCE = '/api/v1/orders/batch/rebalance/'
RESET = '/api/v1/orders/batch/reset/'


class BatchSummaryViewTests(OrdersAPITestCase):

    def test_reports_pending_and_holes(self):
        make_order(self.restaurant, batch_number=1)
        make_order(self.restaurant, batch_number=1, status='pending')
        make_order(self.restaurant, batch_number=2)
        make_order(self.restaurant, batch_number=2, status='done')  # not counted
        rows = self.client.get(SUMMARY, {'window_size': 3}).data['results']
        self.assertEqual(rows, [
            {'batch_number': 1, 'pending': 2, 'holes': 1},
            {'batch_number': 2, 'pending': 1, 'holes': 2},
        ])

    def test_holes_never_negative(self):
        for _ in range(3):
            make_order(self.restaurant, batch_number=1)
        self.assertEqual(self.client.get(SUMMARY, {'window_size': 2}).data['results'][0]['holes'], 0)

    def test_batch_limit_and_paging(self):
        for n in (1, 2, 3):
            make_order(self.restaurant, batch_number=n)
        self.assertEqual(len(self.client.get(SUMMARY, {'batch_limit': 2}).data['results']), 2)
        self.assertEqual(self.client.get(SUMMARY, {'page_size': 1}).data['count'], 3)

    def test_validation(self):
        self.assertEqual(self.client.get(SUMMARY, {'window_size': 'x'}).status_code, 400)

    def test_only_own_restaurant(self):
        make_order(self.other_restaurant, batch_number=7)
        self.assertEqual(self.client.get(SUMMARY).data['results'], [])


class RebalanceViewTests(OrdersAPITestCase):

    def test_promotes_oldest_into_holes(self):
        first = make_order(self.restaurant, batch_number=1, created_minutes_ago=40)
        older = make_order(self.restaurant, batch_number=2, created_minutes_ago=30)
        newer = make_order(self.restaurant, batch_number=2, created_minutes_ago=5)
        response = self.client.post(f'{REBALANCE}?window_size=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['rebalanced'], 1)
        self.assertEqual([reload(o).batch_number for o in (first, older, newer)], [1, 1, 2])

    def test_target_batch(self):
        make_order(self.restaurant, batch_number=1)
        make_order(self.restaurant, batch_number=2)
        make_order(self.restaurant, batch_number=3)
        response = self.client.post(f'{REBALANCE}?window_size=2&batch=2')
        self.assertEqual({c['new_batch'] for c in response.data['changes']}, {2})

    def test_validation(self):
        for query in ('window_size=0', 'batch=0', 'batch=abc'):
            with self.subTest(query):
                self.assertEqual(self.client.post(f'{REBALANCE}?{query}').status_code, 400)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(REBALANCE).status_code, 405)

    def test_customers_are_forbidden(self):
        self.assertEqual(self.as_user(create_customer()).post(REBALANCE).status_code, 403)

    def test_cashiers_may_rebalance_their_restaurant(self):
        self.assertEqual(self.as_user(create_cashier(self.restaurant)).post(REBALANCE).status_code, 200)


class ResetViewTests(OrdersAPITestCase):

    def setUp(self):
        super().setUp()
        self.active = make_order(self.restaurant, batch_number=5)
        self.done = make_order(self.restaurant, batch_number=4, status='done')

    def test_default_mode_resets_completed_only(self):
        response = self.client.post(RESET)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['mode'], 'completed')
        self.assertEqual(response.data['orders_reset'], 1)
        self.assertEqual((reload(self.active).batch_number, reload(self.done).batch_number), (5, 0))

    def test_all_mode_blocked_by_active_orders(self):
        response = self.client.post(f'{RESET}?mode=all')
        self.assertEqual(response.status_code, 400)
        self.assertIn('mode', response.data)

    def test_all_mode_when_kitchen_is_empty(self):
        self.active.status = 'cancelled'
        self.active.save()
        response = self.client.post(f'{RESET}?mode=ALL')  # case-insensitive
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['orders_reset'], 2)

    def test_unknown_mode(self):
        self.assertEqual(self.client.post(f'{RESET}?mode=nuke').status_code, 400)

    def test_does_not_touch_other_restaurants(self):
        foreign = make_order(self.other_restaurant, batch_number=9, status='done')
        self.client.post(RESET)
        self.assertEqual(reload(foreign).batch_number, 9)
