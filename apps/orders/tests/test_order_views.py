"""Restaurant-side order endpoints: auth, CRUD, kitchen board filters."""

from rest_framework import status

from apps.orders.models import Order
from apps.orders.tests.base import (
    OrdersAPITestCase, create_cashier, create_customer, make_order, reload,
)
from apps.restaurants.models import Criteria

LIST = '/api/v1/orders/'


def body(menu_item, qty=1, **extra):
    return {'order_items': [{'menu_item': str(menu_item.pk), 'quantity': qty}], **extra}


class AccessControlTests(OrdersAPITestCase):
    ENDPOINTS = [
        '/api/v1/orders/', '/api/v1/orders/vip/', '/api/v1/orders/windowed/',
        '/api/v1/orders/indoor/normal/windowed/', '/api/v1/orders/outdoor/normal/windowed/',
        '/api/v1/orders/filtered/', '/api/v1/orders/simple/', '/api/v1/orders/batch/summary/',
    ]

    def test_anonymous_gets_401(self):
        client = self.as_user(None)
        for url in self.ENDPOINTS:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customers_cannot_use_kitchen_endpoints(self):
        client = self.as_user(create_customer())
        for url in self.ENDPOINTS:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_and_active_cashier_are_allowed(self):
        cashier = create_cashier(self.restaurant)
        for user in (self.owner, cashier):
            for url in self.ENDPOINTS:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.as_user(user).get(url).status_code, 200)

    def test_inactive_cashier_is_locked_out(self):
        cashier = create_cashier(self.restaurant, is_active=False)
        self.assertEqual(self.as_user(cashier).get(LIST).status_code, 403)

    def test_cashier_sees_only_their_restaurants_orders(self):
        mine = make_order(self.restaurant)
        make_order(self.other_restaurant)
        response = self.as_user(create_cashier(self.restaurant)).get(LIST)
        self.assertEqual(self.ids(response), [self.pk(mine)])


class ListTests(OrdersAPITestCase):

    def test_paginated_shape(self):
        for _ in range(3):
            make_order(self.restaurant, [(self.fries, 1)])
        data = self.client.get(LIST, {'page_size': 2}).data
        self.assertEqual(len(data['results']), 2)
        self.assertEqual(data['count'], 3)
        self.assertEqual(data['total_pages'], 2)
        self.assertEqual(data['next'], 2)
        self.assertIsNone(data['previous'])

    def test_default_order_is_newest_first(self):
        old = make_order(self.restaurant, created_minutes_ago=30)
        new = make_order(self.restaurant, created_minutes_ago=1)
        self.assertEqual(self.ids(self.client.get(LIST)), [self.pk(new), self.pk(old)])

    def test_includes_every_status_and_only_own_restaurant(self):
        done = make_order(self.restaurant, status='done')
        pending = make_order(self.restaurant)
        make_order(self.other_restaurant)
        self.assertCountEqual(self.ids(self.client.get(LIST)), [self.pk(done), self.pk(pending)])

    def test_ordering_parameter(self):
        low = make_order(self.restaurant, score=0.1)
        high = make_order(self.restaurant, score=0.9)
        response = self.client.get(LIST, {'ordering': '-priority_score'})
        self.assertEqual(self.ids(response), [self.pk(high), self.pk(low)])

    def test_invalid_parameters_return_400(self):
        for params in ({'ordering': 'password'}, {'page': '0'}, {'page': 'x'},
                       {'page_size': '101'}, {'page_size': '0'}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(LIST, params).status_code, 400)

    def test_order_payload(self):
        order = make_order(self.restaurant, [(self.fries, 2), (self.burger, 1)], batch_number=1)
        row = self.client.get(LIST).data['results'][0]
        self.assertEqual(row['id'], self.pk(order))
        self.assertEqual(row['order_number'], f'ORD-{str(order.pk)[:4].upper()}')
        self.assertEqual(row['channel'], 'dine_in')
        self.assertEqual(row['total_quantity'], 3)
        self.assertEqual(row['total_prep_time'], 12)
        self.assertAlmostEqual(row['total_cost'], 13.0)
        self.assertEqual({i['menu_item_name'] for i in row['order_items']}, {'Fries', 'Burger'})
        self.assertEqual(row['batch_number'], 1)


class CreateTests(OrdersAPITestCase):

    def test_create_returns_201_with_full_order(self):
        response = self.client.post(LIST, body(self.fries, 2), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['channel'], 'dine_in')
        self.assertEqual(response.data['batch_number'], 1)
        self.assertEqual(response.data['created_by']['username'], 'A_owner')
        self.assertEqual(response.data['total_quantity'], 2)
        self.assertGreater(response.data['priority_score'], 0)
        self.assertEqual(Order.objects.count(), 1)

    def test_orders_fill_a_batch_then_open_the_next(self):
        batches = [
            self.client.post(LIST, body(self.fries), format='json').data['batch_number']
            for _ in range(11)
        ]
        self.assertEqual(batches, [1] * 10 + [2])

    def test_validation_errors(self):
        bad_payloads = {
            'no items': {'order_items': []},
            'missing items': {},
            'zero quantity': body(self.fries, 0),
            'unknown menu item': {'order_items': [{'menu_item': '00000000-0000-0000-0000-000000000000', 'quantity': 1}]},
            'invalid status': {**body(self.fries), 'status': 'teleported'},
        }
        for label, payload in bad_payloads.items():
            with self.subTest(label):
                self.assertEqual(self.client.post(LIST, payload, format='json').status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_order_item_without_menu_item_is_a_400(self):
        """A missing/null menu_item should be rejected."""
        response = self.client.post(LIST, {'order_items': [{'quantity': 2}]}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_delivery_orders_cannot_be_created_here(self):
        for flag in (False, 'false'):
            with self.subTest(flag=flag):
                response = self.client.post(LIST, body(self.fries, is_indoor=flag), format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('is_indoor', response.data)

    def test_cashier_vip_permission(self):
        denied = self.as_user(create_cashier(self.restaurant, 'c1'))
        allowed = self.as_user(create_cashier(self.restaurant, 'c2', can_set_vip=True))
        self.assertEqual(denied.post(LIST, body(self.fries, special_flag=True), format='json').status_code, 400)
        self.assertEqual(denied.post(LIST, body(self.fries), format='json').status_code, 201)
        response = allowed.post(LIST, body(self.fries, special_flag=True), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['special_flag'])

    def test_customer_cannot_create_dine_in_orders(self):
        client = self.as_user(create_customer())
        self.assertEqual(client.post(LIST, body(self.fries), format='json').status_code, 403)


class DetailTests(OrdersAPITestCase):

    def setUp(self):
        super().setUp()
        self.order = make_order(self.restaurant, [(self.fries, 1)], batch_number=1)
        self.url = f'/api/v1/orders/{self.order.pk}/'

    def test_retrieve(self):
        self.assertEqual(self.client.get(self.url).data['id'], self.pk(self.order))

    def test_other_restaurants_order_is_404_for_every_method(self):
        foreign = make_order(self.other_restaurant, [(self.other_menu['fries'], 1)])
        url = f'/api/v1/orders/{foreign.pk}/'
        for method, kwargs in (('get', {}), ('patch', {'data': {'status': 'done'}}),
                               ('put', {'data': body(self.fries)}), ('delete', {})):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url, format='json', **kwargs).status_code, 404)
        self.assertEqual(reload(foreign).status, 'pending')

    def test_unknown_id_is_404(self):
        self.assertEqual(self.client.get('/api/v1/orders/00000000-0000-0000-0000-000000000000/').status_code, 404)

    def test_patch_status(self):
        response = self.client.patch(self.url, {'status': 'done'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(reload(self.order).status, 'done')

    def test_patch_items_replaces_them_and_rescores(self):
        before = reload(self.order).priority_score
        response = self.client.patch(self.url, body(self.steak, 4), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([i['menu_item_name'] for i in response.data['order_items']], ['Steak'])
        self.assertLess(response.data['priority_score'], before)

    def test_put_requires_items(self):
        self.assertEqual(self.client.put(self.url, {'status': 'done'}, format='json').status_code, 400)
        self.assertEqual(self.client.put(self.url, body(self.burger, 2), format='json').status_code, 200)

    def test_finished_orders_are_read_only(self):
        for status_ in ('done', 'cancelled'):
            with self.subTest(status=status_):
                order = make_order(self.restaurant, [(self.fries, 1)], status=status_)
                response = self.client.patch(f'/api/v1/orders/{order.pk}/', {'status': 'pending'}, format='json')
                self.assertEqual(response.status_code, 400)

    def test_batch_number_cannot_be_changed_through_the_api(self):
        self.client.patch(self.url, {'status': 'done', 'batch_number': 42}, format='json')
        self.assertEqual(reload(self.order).batch_number, 1)

    def test_delete_cancels_instead_of_deleting(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(reload(self.order).status, 'cancelled')

    def test_delete_twice_is_400(self):
        self.client.delete(self.url)
        self.assertEqual(self.client.delete(self.url).status_code, 400)

    def test_cashier_vip_toggle_requires_permission(self):
        plain = self.as_user(create_cashier(self.restaurant, 'c1'))
        vip = self.as_user(create_cashier(self.restaurant, 'c2', can_set_vip=True))
        self.assertEqual(plain.patch(self.url, {'special_flag': True}, format='json').status_code, 400)
        self.assertEqual(vip.patch(self.url, {'special_flag': True}, format='json').status_code, 200)


class KitchenBoardTests(OrdersAPITestCase):
    """windowed / vip / indoor / outdoor / filtered / simple."""

    def setUp(self):
        super().setUp()
        self.customer = create_customer()
        self.vip = make_order(self.restaurant, special_flag=True, batch_number=1, score=0.1)
        self.high = make_order(self.restaurant, batch_number=1, score=0.9)
        self.low = make_order(self.restaurant, batch_number=1, score=0.2)
        self.next_batch = make_order(self.restaurant, batch_number=2, score=0.95)
        self.delivery = make_order(self.restaurant, is_indoor=False, customer=self.customer,
                                   batch_number=2, score=0.5)
        self.done = make_order(self.restaurant, status='done', batch_number=1)

    def get_ids(self, url, **params):
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200, response.data)
        return self.ids(response)

    def test_windowed_is_batch_then_vip_then_score(self):
        self.assertEqual(self.get_ids('/api/v1/orders/windowed/'), [
            self.pk(self.vip), self.pk(self.high), self.pk(self.low),
            self.pk(self.next_batch), self.pk(self.delivery),
        ])

    def test_windowed_excludes_finished_orders_by_default(self):
        self.assertNotIn(self.pk(self.done), self.get_ids('/api/v1/orders/windowed/'))

    def test_windowed_filters(self):
        self.assertEqual(self.get_ids('/api/v1/orders/windowed/', status='done'), [self.pk(self.done)])
        self.assertEqual(self.get_ids('/api/v1/orders/windowed/', is_indoor='false'), [self.pk(self.delivery)])
        self.assertEqual(
            self.get_ids('/api/v1/orders/windowed/', batch_limit=1),
            [self.pk(self.vip), self.pk(self.high), self.pk(self.low)],
        )

    def test_vip_endpoint(self):
        self.assertEqual(self.get_ids('/api/v1/orders/vip/'), [self.pk(self.vip)])

    def test_indoor_and_outdoor_normal_endpoints(self):
        self.assertEqual(self.get_ids('/api/v1/orders/indoor/normal/windowed/'),
                         [self.pk(self.high), self.pk(self.low), self.pk(self.next_batch)])
        self.assertEqual(self.get_ids('/api/v1/orders/outdoor/normal/windowed/'), [self.pk(self.delivery)])

    def test_filtered_scope(self):
        self.assertEqual(self.get_ids('/api/v1/orders/filtered/', scope='vip'), [self.pk(self.vip)])
        normal = self.get_ids('/api/v1/orders/filtered/', scope='normal')
        self.assertNotIn(self.pk(self.vip), normal)
        self.assertEqual(len(normal), 4)

    def test_filtered_unwindowed_is_pure_priority(self):
        ids = self.get_ids('/api/v1/orders/filtered/', windowed='false')
        self.assertEqual(ids[0], self.pk(self.vip))           # VIP always first
        self.assertEqual(ids[1], self.pk(self.next_batch))    # 0.95 beats batch order

    def test_filtered_limit_and_paging(self):
        self.assertEqual(len(self.get_ids('/api/v1/orders/filtered/', limit=2)), 2)
        response = self.client.get('/api/v1/orders/filtered/', {'page_size': 2, 'page': 2})
        self.assertEqual(response.data['current_page'], 2)
        self.assertEqual(len(response.data['results']), 2)

    def test_invalid_query_parameters(self):
        cases = [
            ('/api/v1/orders/windowed/', {'status': 'bogus'}),
            ('/api/v1/orders/windowed/', {'is_indoor': 'maybe'}),
            ('/api/v1/orders/windowed/', {'window_size': '0'}),
            ('/api/v1/orders/windowed/', {'batch_limit': '0'}),
            ('/api/v1/orders/windowed/', {'ordering': 'secret'}),
            ('/api/v1/orders/filtered/', {'scope': 'everything'}),
            ('/api/v1/orders/filtered/', {'windowed': 'sometimes'}),
            ('/api/v1/orders/filtered/', {'limit': '-3'}),
        ]
        for url, params in cases:
            with self.subTest(url=url, params=params):
                self.assertEqual(self.client.get(url, params).status_code, 400)

    def test_other_restaurants_orders_never_leak(self):
        foreign = make_order(self.other_restaurant, special_flag=True, batch_number=1)
        for url in ('/api/v1/orders/windowed/', '/api/v1/orders/vip/', '/api/v1/orders/filtered/'):
            with self.subTest(url=url):
                self.assertNotIn(self.pk(foreign), self.get_ids(url))


class SimpleOrdersViewTests(OrdersAPITestCase):
    URL = '/api/v1/orders/simple/'

    def test_empty_without_criteria(self):
        make_order(self.restaurant, [(self.fries, 1)])
        self.assertEqual(self.client.get(self.URL).data['results'], [])

    def test_returns_matching_orders_and_supports_ordering(self):
        Criteria.objects.create(restaurant=self.restaurant, max_quantity=2, min_category_priority=3)
        old = make_order(self.restaurant, [(self.fries, 1)], created_minutes_ago=20, score=0.1)
        new = make_order(self.restaurant, [(self.fries, 2)], created_minutes_ago=1, score=0.9)
        make_order(self.restaurant, [(self.steak, 1)])    # priority too low
        make_order(self.restaurant, [(self.fries, 5)])    # too many items
        self.assertEqual(self.ids(self.client.get(self.URL)), [self.pk(old), self.pk(new)])
        by_score = self.client.get(self.URL, {'ordering': '-priority_score'})
        self.assertEqual(self.ids(by_score), [self.pk(new), self.pk(old)])
