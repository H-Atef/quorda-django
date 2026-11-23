"""Order-item endpoints."""

from apps.orders.tests.base import (
    OrdersAPITestCase, create_cashier, create_customer, make_order, reload,
)


class ItemViewsBase(OrdersAPITestCase):

    def setUp(self):
        super().setUp()
        self.order = make_order(self.restaurant, [(self.fries, 1), (self.burger, 2)], batch_number=1)
        self.fries_item = self.order.order_items.get(menu_item=self.fries)
        self.items_url = f'/api/v1/orders/{self.order.pk}/items/'

    def item_url(self, item, order=None):
        return f'/api/v1/orders/{(order or self.order).pk}/items/{item.pk}/'


class ItemListAndAddTests(ItemViewsBase):

    def test_list_items(self):
        response = self.client.get(self.items_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({r['menu_item_name'] for r in response.data}, {'Fries', 'Burger'})

    def test_add_item_snapshots_price_and_rescores(self):
        before = reload(self.order).priority_score
        response = self.client.post(self.items_url, {'menu_item': str(self.steak.pk), 'quantity': 3}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['unit_price'], '18.00')
        self.assertEqual(self.order.order_items.count(), 3)
        self.assertLess(reload(self.order).priority_score, before)

    def test_add_validation(self):
        for payload in ({}, {'menu_item': str(self.steak.pk), 'quantity': 0},
                        {'menu_item': 'not-a-uuid', 'quantity': 1}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(self.items_url, payload, format='json').status_code, 400)

    def test_menu_item_is_required_when_adding_an_item(self):
        """
        OrderItem.menu_item is required, so omitting it must be rejected with 400
        instead of crashing with KeyError (HTTP 500).
        """
        response = self.client.post(self.items_url, {'quantity': 2}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_cannot_add_to_finished_order(self):
        for status in ('done', 'cancelled'):
            with self.subTest(status=status):
                order = make_order(self.restaurant, [(self.fries, 1)], status=status)
                url = f'/api/v1/orders/{order.pk}/items/'
                self.assertEqual(self.client.post(url, {'menu_item': str(self.steak.pk), 'quantity': 1}, format='json').status_code, 400)

    def test_other_restaurants_order_is_404(self):
        foreign = make_order(self.other_restaurant, [(self.other_menu['fries'], 1)])
        url = f'/api/v1/orders/{foreign.pk}/items/'
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'menu_item': str(self.steak.pk), 'quantity': 1}, format='json').status_code, 404)

    def test_access_control(self):
        self.assertEqual(self.as_user(None).get(self.items_url).status_code, 401)
        self.assertEqual(self.as_user(create_customer()).get(self.items_url).status_code, 403)
        self.assertEqual(self.as_user(create_cashier(self.restaurant)).get(self.items_url).status_code, 200)


class ItemDetailTests(ItemViewsBase):

    def test_retrieve(self):
        response = self.client.get(self.item_url(self.fries_item))
        self.assertEqual(response.data['menu_item_name'], 'Fries')

    def test_patch_quantity_rescores(self):
        before = reload(self.order).priority_score
        response = self.client.patch(self.item_url(self.fries_item), {'quantity': 9}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['quantity'], 9)
        self.assertLess(reload(self.order).priority_score, before)

    def test_put_changes_menu_item_and_price_snapshot(self):
        response = self.client.put(
            self.item_url(self.fries_item), {'menu_item': str(self.steak.pk), 'quantity': 1}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['unit_price'], '18.00')

    def test_put_requires_quantity(self):
        payload = {'menu_item': str(self.steak.pk)}
        self.assertEqual(self.client.put(self.item_url(self.fries_item), payload, format='json').status_code, 400)

    def test_delete_item_rescores(self):
        response = self.client.delete(self.item_url(self.fries_item))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.order.order_items.count(), 1)

    def test_finished_orders_are_read_only(self):
        self.order.status = 'done'
        self.order.save()
        url = self.item_url(self.fries_item)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.patch(url, {'quantity': 2}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 400)
        self.assertEqual(self.order.order_items.count(), 2)

    def test_item_must_belong_to_the_order_in_the_url(self):
        other = make_order(self.restaurant, [(self.steak, 1)])
        foreign_item = other.order_items.get()
        self.assertEqual(self.client.get(self.item_url(foreign_item)).status_code, 404)
        self.assertEqual(self.client.delete(self.item_url(foreign_item)).status_code, 404)

    def test_other_restaurants_item_is_404(self):
        foreign = make_order(self.other_restaurant, [(self.other_menu['fries'], 1)])
        item = foreign.order_items.get()
        url = self.item_url(item, order=foreign)
        for method in ('get', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url, format='json').status_code, 404)
        self.assertEqual(foreign.order_items.count(), 1)
