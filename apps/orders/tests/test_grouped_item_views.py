"""GET /api/v1/orders/items/grouped/ : the kitchen prep list."""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from apps.orders.tests.base import OrdersAPITestCase, create_cashier, create_customer, make_order

URL = '/api/v1/orders/items/grouped/'


class GroupedItemsViewTests(OrdersAPITestCase):

    def names(self, response):
        return [row['name'] for row in response.data['results']]

    def test_response_shape(self):
        order = make_order(self.restaurant, [(self.burger, 2)], batch_number=1)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['orders_considered'], 1)
        self.assertEqual(response.data['count'], 1)
        group = response.data['results'][0]
        self.assertEqual(group['menu_item'], str(self.burger.pk))
        self.assertEqual((group['name'], group['category'], group['prep_time']), ('Burger', 'cat3', 10))
        self.assertEqual((group['total_quantity'], group['order_count']), (2, 1))
        self.assertEqual((group['first_queue_position'], group['spans_batches']), (1, False))
        line = group['orders'][0]
        self.assertEqual(line['order_id'], str(order.pk))
        self.assertEqual(line['order_number'], f'ORD-{str(order.pk)[:4].upper()}')
        self.assertEqual((line['queue_position'], line['batch_number'], line['quantity']), (1, 1, 2))
        self.assertEqual((line['special_flag'], line['channel']), (False, 'dine_in'))

    def test_groups_the_same_item_across_orders(self):
        make_order(self.restaurant, [(self.burger, 1)], batch_number=1, score=0.9)
        make_order(self.restaurant, [(self.burger, 3), (self.fries, 1)], batch_number=1, score=0.5)
        response = self.client.get(URL)
        self.assertEqual(self.names(response), ['Burger', 'Fries'])
        self.assertEqual(response.data['results'][0]['total_quantity'], 4)
        self.assertEqual([l['queue_position'] for l in response.data['results'][0]['orders']], [1, 2])

    def test_empty_queue(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data['orders_considered'], response.data['results']), (0, []))

    def test_batch_limit_default_and_override(self):
        make_order(self.restaurant, [(self.fries, 1)], batch_number=1)
        make_order(self.restaurant, [(self.steak, 1)], batch_number=2)
        self.assertEqual(self.names(self.client.get(URL)), ['Fries'])
        self.assertEqual(self.names(self.client.get(URL, {'batch_limit': 2})), ['Fries', 'Steak'])

    def test_windowed_false_is_priority_order(self):
        make_order(self.restaurant, [(self.fries, 1)], batch_number=1, score=0.1)
        make_order(self.restaurant, [(self.steak, 1)], batch_number=2, score=0.9)
        response = self.client.get(URL, {'windowed': 'false'})
        self.assertEqual(self.names(response), ['Steak', 'Fries'])

    def test_scope_and_is_indoor_filters(self):
        make_order(self.restaurant, [(self.fries, 1)], special_flag=True, batch_number=1)
        make_order(self.restaurant, [(self.steak, 1)], batch_number=1)
        make_order(self.restaurant, [(self.burger, 1)], is_indoor=False,
                   customer=create_customer(), batch_number=1)
        self.assertEqual(self.names(self.client.get(URL, {'scope': 'vip'})), ['Fries'])
        self.assertEqual(sorted(self.names(self.client.get(URL, {'scope': 'normal'}))), ['Burger', 'Steak'])
        self.assertEqual(self.names(self.client.get(URL, {'is_indoor': 'false'})), ['Burger'])

    def test_pagination(self):
        make_order(self.restaurant, [(self.fries, 1), (self.burger, 1), (self.steak, 1)], batch_number=1)
        response = self.client.get(URL, {'page_size': 2})
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual((response.data['count'], response.data['total_pages']), (3, 2))
        self.assertEqual(len(self.client.get(URL, {'page_size': 2, 'page': 2}).data['results']), 1)

    def test_validation(self):
        for query in ({'batch_limit': 0}, {'batch_limit': 'x'}, {'windowed': 'maybe'},
                      {'scope': 'everyone'}, {'is_indoor': 'sometimes'}, {'page_size': 101}, {'page': 0}):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(URL, query).status_code, 400)

    def test_only_own_restaurant(self):
        make_order(self.other_restaurant, [(self.other_menu['burger'], 9)], batch_number=1)
        self.assertEqual(self.client.get(URL).data['results'], [])


class GroupedItemsPermissionTests(OrdersAPITestCase):

    def test_anonymous_gets_401(self):
        self.assertEqual(self.as_user(None).get(URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_gets_403(self):
        self.assertEqual(self.as_user(create_customer()).get(URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_and_active_cashier_allowed_inactive_cashier_blocked(self):
        active = create_cashier(self.restaurant, 'active')
        inactive = create_cashier(self.restaurant, 'inactive', is_active=False)
        self.assertEqual(self.as_user(self.owner).get(URL).status_code, 200)
        self.assertEqual(self.as_user(active).get(URL).status_code, 200)
        self.assertEqual(self.as_user(inactive).get(URL).status_code, 403)

    def test_read_only(self):
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(URL).status_code, 405)


class GroupedItemsQueryCountTests(OrdersAPITestCase):

    def test_query_count_does_not_grow_with_order_count(self):
        def run():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(URL, {'batch_limit': 5}).status_code, 200)
            return len(ctx)

        make_order(self.restaurant, [(self.fries, 1)], batch_number=1)
        small = run()
        for _ in range(15):
            make_order(self.restaurant, [(self.fries, 1), (self.steak, 2), (self.burger, 1)], batch_number=1)
        self.assertEqual(run(), small)
