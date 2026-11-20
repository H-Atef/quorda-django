"""Customer (delivery) endpoints under /orders/customers/."""
from apps.orders.models import Order
from apps.orders.tests.base import (
    OrdersAPITestCase, create_cashier, create_customer, make_order, reload,
)

BASE = '/api/v1/orders/customers/'


class CustomerViewsBase(OrdersAPITestCase):

    def setUp(self):
        super().setUp()
        self.customer = create_customer('c1')
        self.other_customer = create_customer('c2')
        self.client = self.as_user(self.customer)

    def place(self, client=None, menu_item=None, qty=1, restaurant=None):
        payload = {
            'restaurant': str((restaurant or self.restaurant).pk),
            'order_items': [{'menu_item': str((menu_item or self.burger).pk), 'quantity': qty}],
        }
        return (client or self.client).post(BASE, payload, format='json')

    def delivery(self, customer=None, **kw):
        return make_order(self.restaurant, [(self.fries, 1)], is_indoor=False,
                          customer=customer or self.customer, **kw)


class PlaceOrderTests(CustomerViewsBase):

    def test_place_delivery_order(self):
        response = self.place(qty=2)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['channel'], 'delivery')
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(str(response.data['customer']), str(self.customer.pk))
        self.assertFalse(response.data['special_flag'])
        order = Order.objects.get()
        self.assertFalse(order.is_indoor)
        self.assertEqual(order.created_by, self.customer)

    def test_customer_cannot_force_vip_or_dine_in(self):
        payload = {
            'restaurant': str(self.restaurant.pk), 'special_flag': True, 'is_indoor': True,
            'order_items': [{'menu_item': str(self.burger.pk), 'quantity': 1}],
        }
        response = self.client.post(BASE, payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['special_flag'])
        self.assertEqual(response.data['channel'], 'delivery')

    def test_validation(self):
        good_items = [{'menu_item': str(self.burger.pk), 'quantity': 1}]
        cases = {
            'no items': {'restaurant': str(self.restaurant.pk), 'order_items': []},
            'no restaurant': {'order_items': good_items},
            'unknown restaurant': {'restaurant': '00000000-0000-0000-0000-000000000000', 'order_items': good_items},
            'zero quantity': {'restaurant': str(self.restaurant.pk),
                              'order_items': [{'menu_item': str(self.burger.pk), 'quantity': 0}]},
        }
        for label, payload in cases.items():
            with self.subTest(label):
                self.assertEqual(self.client.post(BASE, payload, format='json').status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_inactive_restaurant_is_rejected(self):
        self.restaurant.is_active = False
        self.restaurant.save()
        self.assertEqual(self.place().status_code, 400)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.as_user(None).get(BASE).status_code, 401)
        self.assertEqual(self.as_user(None).post(BASE, {}, format='json').status_code, 401)

    def test_delivery_order_shows_up_on_the_kitchen_board(self):
        order_id = self.place().data['id']
        kitchen = self.as_user(self.owner).get('/api/v1/orders/outdoor/normal/windowed/')
        self.assertIn(order_id, self.ids(kitchen))


class ListAndDetailTests(CustomerViewsBase):

    def test_list_returns_only_my_delivery_orders(self):
        mine = self.delivery()
        self.delivery(customer=self.other_customer)
        make_order(self.restaurant, customer=self.customer, is_indoor=True)   # dine-in
        response = self.client.get(BASE)
        self.assertEqual(self.ids(response), [self.pk(mine)])
        self.assertEqual(response.data['count'], 1)

    def test_list_includes_finished_orders(self):
        done = self.delivery(status='done')
        self.assertEqual(self.ids(self.client.get(BASE)), [self.pk(done)])

    def test_retrieve_own_order(self):
        order = self.delivery()
        self.assertEqual(self.client.get(f'{BASE}{order.pk}/').data['id'], self.pk(order))

    def test_other_customers_order_is_404(self):
        order = self.delivery(customer=self.other_customer)
        for method in ('get', 'patch'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(f'{BASE}{order.pk}/', format='json').status_code, 404)
        self.assertEqual(self.client.post(f'{BASE}{order.pk}/cancel/').status_code, 404)

    def test_dine_in_order_is_not_reachable(self):
        dine_in = make_order(self.restaurant, customer=self.customer, is_indoor=True)
        self.assertEqual(self.client.get(f'{BASE}{dine_in.pk}/').status_code, 404)

    def test_pagination_validation(self):
        self.assertEqual(self.client.get(BASE, {'page_size': '500'}).status_code, 400)


class UpdateAndCancelTests(CustomerViewsBase):

    def test_patch_items(self):
        order = self.delivery()
        payload = {'order_items': [{'menu_item': str(self.steak.pk), 'quantity': 3}]}
        response = self.client.patch(f'{BASE}{order.pk}/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['total_quantity'], 3)
        self.assertEqual(reload(order).order_items.get().menu_item, self.steak)

    def test_patch_with_empty_items_is_rejected(self):
        order = self.delivery()
        self.assertEqual(self.client.patch(f'{BASE}{order.pk}/', {'order_items': []}, format='json').status_code, 400)
        self.assertEqual(reload(order).order_items.count(), 1)

    def test_cannot_edit_once_finished(self):
        order = self.delivery(status='done')
        payload = {'order_items': [{'menu_item': str(self.steak.pk), 'quantity': 1}]}
        self.assertEqual(self.client.patch(f'{BASE}{order.pk}/', payload, format='json').status_code, 400)

    def test_cancel(self):
        order = self.delivery()
        response = self.client.post(f'{BASE}{order.pk}/cancel/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'cancelled')

    def test_cannot_cancel_twice_or_after_done(self):
        for status in ('cancelled', 'done'):
            with self.subTest(status=status):
                order = self.delivery(status=status)
                self.assertEqual(self.client.post(f'{BASE}{order.pk}/cancel/').status_code, 400)

    def test_restaurant_staff_use_the_other_endpoints(self):
        """Owners/cashiers have no ownership of a customer's order on the customer routes."""
        order = self.delivery()
        for user in (self.owner, create_cashier(self.restaurant)):
            with self.subTest(user=user.username):
                self.assertEqual(self.as_user(user).get(f'{BASE}{order.pk}/').status_code, 404)
