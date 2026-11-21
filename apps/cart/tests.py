from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.cart.exceptions import CartConflict
from apps.cart.models import Cart, CartItem
from apps.cart.services import CartService
from apps.orders.models import Order, OrderItem
from apps.restaurants.models import Category, MenuItem
from apps.users.models import RestaurantProfile, User


TEST_SETTINGS = {
    'DATABASES': {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    'PASSWORD_HASHERS': ['django.contrib.auth.hashers.MD5PasswordHasher'],
}


class CartTestMixin:
    @classmethod
    def make_user(cls, username, role, email=None, password='pass12345'):
        return User.objects.create_user(
            username=username,
            password=password,
            role=role,
            email=email or f'{username}@example.com',
        )

    @classmethod
    def make_customer(cls, suffix='c1'):
        return cls.make_user(f'cust_{suffix}', 'customer')

    @classmethod
    def make_owner(cls, suffix='o1'):
        return cls.make_user(f'own_{suffix}', 'restaurant')

    @classmethod
    def make_cashier(cls, suffix='cash1', restaurant=None):
        user = cls.make_user(f'cash_{suffix}', 'cashier')
        if restaurant is None:
            restaurant = cls.make_restaurant(suffix=f'cashrest_{suffix}')
        from apps.users.models import CashierProfile
        CashierProfile.objects.create(user=user, restaurant=restaurant)
        return user, restaurant

    @classmethod
    def make_admin(cls, suffix='a1'):
        return cls.make_user(f'adm_{suffix}', 'admin')

    @classmethod
    def make_restaurant(cls, suffix='r1', is_active=True):
        user = cls.make_user(f'rest_{suffix}', 'restaurant')
        return RestaurantProfile.objects.create(
            user=user,
            restaurant_name=f'Restaurant {suffix}',
            address='123 Test St',
            is_active=is_active,
        )

    @classmethod
    def make_category(cls, restaurant, name, priority=3):
        return Category.objects.create(restaurant=restaurant, name=name, priority=priority)

    @classmethod
    def make_item(cls, restaurant, name, category, prep_time=5, price='10.00', is_available=True):
        return MenuItem.objects.create(
            restaurant=restaurant,
            name=name,
            category=category,
            prep_time=prep_time,
            price=Decimal(price),
            is_available=is_available,
        )

    @classmethod
    def authenticate(cls, client, user):
        client.force_authenticate(user=user)


@override_settings(**TEST_SETTINGS)
class CartAccessControlTests(CartTestMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = cls.make_customer('ac')
        cls.owner = cls.make_owner('ac')
        cls.admin = cls.make_admin('ac')
        cls.cashier, _ = cls.make_cashier('ac')
        cls.restaurant = cls.make_restaurant('ac')
        cls.category = cls.make_category(cls.restaurant, 'mains', 3)
        cls.item = cls.make_item(cls.restaurant, 'pie', cls.category, price='10.00')

    def setUp(self):
        self.client = APIClient()

    def test_anonymous_get_cart_401(self):
        resp = self.client.get('/api/v1/cart/')
        self.assertEqual(resp.status_code, 401)

    def test_anonymous_add_item_401(self):
        resp = self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 1})
        self.assertEqual(resp.status_code, 401)

    def test_anonymous_checkout_401(self):
        resp = self.client.post('/api/v1/cart/checkout/', {})
        self.assertEqual(resp.status_code, 401)

    def test_owner_cannot_access_cart_403(self):
        self.authenticate(self.client, self.owner)
        resp = self.client.get('/api/v1/cart/')
        self.assertEqual(resp.status_code, 403)

    def test_cashier_cannot_access_cart_403(self):
        self.authenticate(self.client, self.cashier)
        resp = self.client.get('/api/v1/cart/')
        self.assertEqual(resp.status_code, 403)

    def test_admin_cannot_access_cart_403(self):
        self.authenticate(self.client, self.admin)
        resp = self.client.get('/api/v1/cart/')
        self.assertEqual(resp.status_code, 403)

    def test_customer_isolation(self):
        other = self.make_customer('ac2')
        self.authenticate(self.client, self.customer)
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 2})
        self.authenticate(self.client, other)
        resp = self.client.get('/api/v1/cart/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['summary']['item_count'], 0)
        self.assertEqual(len(resp.data['items']), 0)


@override_settings(**TEST_SETTINGS)
class CartAddItemTests(CartTestMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = cls.make_customer('add')
        cls.restaurant = cls.make_restaurant('add')
        cls.category = cls.make_category(cls.restaurant, 'mains', 3)
        cls.item = cls.make_item(cls.restaurant, 'pie', cls.category, price='10.00')
        cls.other_restaurant = cls.make_restaurant('add2')
        cls.other_category = cls.make_category(cls.other_restaurant, 'mains', 3)
        cls.other_item = cls.make_item(cls.other_restaurant, 'cake', cls.other_category, price='5.00')
        cls.unavailable_item = cls.make_item(cls.restaurant, 'gone', cls.category, price='1.00', is_available=False)
        cls.inactive_restaurant = cls.make_restaurant('add3', is_active=False)
        cls.inactive_category = cls.make_category(cls.inactive_restaurant, 'mains', 3)
        cls.inactive_item = cls.make_item(cls.inactive_restaurant, 'stale', cls.inactive_category, price='1.00')

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.client, self.customer)

    def _add(self, payload=None, **kwargs):
        data = {'menu_item': str(self.item.id), 'quantity': 1}
        if payload:
            data.update(payload)
        data.update(kwargs)
        return self.client.post('/api/v1/cart/items/', data, format='json')

    def test_add_first_item_creates_cart_and_sets_restaurant(self):
        resp = self._add()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['status'], 'active')
        self.assertEqual(resp.data['restaurant']['restaurant_name'], self.restaurant.restaurant_name)
        self.assertEqual(len(resp.data['items']), 1)
        line = resp.data['items'][0]
        self.assertEqual(line['quantity'], 1)
        self.assertEqual(line['unit_price'], '10.00')
        self.assertEqual(line['added_price'], '10.00')
        self.assertEqual(line['line_total'], '10.00')
        self.assertTrue(line['is_available'])
        self.assertFalse(line['price_changed'])
        self.assertEqual(resp.data['summary']['item_count'], 1)
        self.assertEqual(resp.data['summary']['distinct_items'], 1)
        self.assertEqual(resp.data['summary']['subtotal'], '10.00')
        self.assertTrue(resp.data['can_checkout'])
        self.assertFalse(resp.data['requires_price_confirmation'])
        self.assertEqual(resp.data['issues'], [])

    def test_adding_same_item_merges_quantity(self):
        self._add({'quantity': 2})
        resp = self._add({'quantity': 3})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['summary']['item_count'], 5)
        self.assertEqual(resp.data['summary']['distinct_items'], 1)
        line = resp.data['items'][0]
        self.assertEqual(line['quantity'], 5)
        self.assertEqual(line['line_total'], '50.00')

    def test_different_items_increase_distinct_count(self):
        item2 = self.make_item(self.restaurant, 'cake', self.category, price='5.00')
        self._add()
        resp = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(item2.id), 'quantity': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['summary']['distinct_items'], 2)
        self.assertEqual(resp.data['summary']['item_count'], 2)
        self.assertEqual(resp.data['restaurant']['restaurant_name'], self.restaurant.restaurant_name)

    def test_quantity_zero_400(self):
        resp = self._add({'quantity': 0})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('quantity', resp.data)

    def test_quantity_negative_400(self):
        resp = self._add({'quantity': -1})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('quantity', resp.data)

    def test_quantity_non_integer_400(self):
        resp = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(self.item.id), 'quantity': 'abc'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('quantity', resp.data)

    def test_quantity_float_400(self):
        resp = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(self.item.id), 'quantity': 2.5},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('quantity', resp.data)

    def test_unknown_menu_item_400(self):
        import uuid
        resp = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(uuid.uuid4()), 'quantity': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('menu_item', resp.data)

    def test_malformed_menu_item_id_400(self):
        resp = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': 'not-a-uuid', 'quantity': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('menu_item', resp.data)

    def test_unavailable_item_400(self):
        resp = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(self.unavailable_item.id), 'quantity': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('menu_item', resp.data)

    def test_inactive_restaurant_item_400(self):
        resp = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(self.inactive_item.id), 'quantity': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('menu_item', resp.data)

    def test_max_units_per_item_limit(self):
        resp = self._add({'quantity': 21})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('quantity', resp.data)

    def test_merge_exceeds_max_units_per_item(self):
        self._add({'quantity': 15})
        resp = self._add({'quantity': 10})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('quantity', resp.data)

    def test_max_distinct_items_limit(self):
        from apps.restaurants.models import Category as Cat, MenuItem as MI
        cats = []
        items = []
        for i in range(30):
            cat = Cat.objects.create(restaurant=self.restaurant, name=f'cat{i}', priority=1)
            it = MI.objects.create(restaurant=self.restaurant, name=f'it{i}', category=cat, prep_time=1, price='1.00')
            cats.append(cat)
            items.append(it)
        for it in items:
            self.client.post('/api/v1/cart/items/', {'menu_item': str(it.id), 'quantity': 1}, format='json')
        resp = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(self.item.id), 'quantity': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('cart', resp.data)


@override_settings(**TEST_SETTINGS)
class CartSingleRestaurantTests(CartTestMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = cls.make_customer('sr')
        cls.restaurant = cls.make_restaurant('sr')
        cls.category = cls.make_category(cls.restaurant, 'mains', 3)
        cls.item = cls.make_item(cls.restaurant, 'pie', cls.category, price='10.00')
        cls.other_restaurant = cls.make_restaurant('sr2')
        cls.other_category = cls.make_category(cls.other_restaurant, 'mains', 3)
        cls.other_item = cls.make_item(cls.other_restaurant, 'cake', cls.other_category, price='5.00')

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.client, self.customer)

    def test_adding_other_restaurant_item_returns_409_restaurant_mismatch(self):
        self._add_item(self.item)
        resp = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(self.other_item.id), 'quantity': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data['code'], 'restaurant_mismatch')
        self.assertEqual(resp.data['current_restaurant']['restaurant_name'], self.restaurant.restaurant_name)
        self.assertEqual(resp.data['requested_restaurant']['restaurant_name'], self.other_restaurant.restaurant_name)
        self.assertIn('detail', resp.data)

    def test_replace_cart_starts_over(self):
        self._add_item(self.item)
        resp = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(self.other_item.id), 'quantity': 1, 'replace_cart': True},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['restaurant']['restaurant_name'], self.other_restaurant.restaurant_name)
        self.assertEqual(len(resp.data['items']), 1)
        self.assertEqual(resp.data['items'][0]['name'], 'cake')

    def test_emptying_cart_frees_restaurant(self):
        self._add_item(self.item)
        self.client.delete('/api/v1/cart/items/')  # not valid; clear via DELETE /
        resp = self.client.delete('/api/v1/cart/')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data['restaurant'])
        self.assertEqual(len(resp.data['items']), 0)
        # can now add from another restaurant
        resp2 = self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(self.other_item.id), 'quantity': 1},
            format='json',
        )
        self.assertEqual(resp2.status_code, 201)
        self.assertEqual(resp2.data['restaurant']['restaurant_name'], self.other_restaurant.restaurant_name)

    def _add_item(self, item, quantity=1, replace_cart=False):
        return self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(item.id), 'quantity': quantity, 'replace_cart': replace_cart},
            format='json',
        )


@override_settings(**TEST_SETTINGS)
class CartItemMutationTests(CartTestMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = cls.make_customer('mut')
        cls.other_customer = cls.make_customer('mut2')
        cls.restaurant = cls.make_restaurant('mut')
        cls.category = cls.make_category(cls.restaurant, 'mains', 3)
        cls.item = cls.make_item(cls.restaurant, 'pie', cls.category, price='10.00')
        cls.item2 = cls.make_item(cls.restaurant, 'cake', cls.category, price='5.00')

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.client, self.customer)
        self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(self.item.id), 'quantity': 2},
            format='json',
        )
        self.cart_resp = self.client.get('/api/v1/cart/')
        self.line_id = str(self.cart_resp.data['items'][0]['id'])

    def test_set_quantity(self):
        resp = self.client.patch(
            f'/api/v1/cart/items/{self.line_id}/',
            {'quantity': 4},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        line = resp.data['items'][0]
        self.assertEqual(line['quantity'], 4)
        self.assertEqual(line['line_total'], '40.00')

    def test_set_quantity_zero_400(self):
        resp = self.client.patch(
            f'/api/v1/cart/items/{self.line_id}/',
            {'quantity': 0},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_remove_line(self):
        resp = self.client.delete(f'/api/v1/cart/items/{self.line_id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['items']), 0)
        self.assertIsNone(resp.data['restaurant'])

    def test_remove_another_customers_line_404(self):
        self.authenticate(self.client, self.other_customer)
        resp = self.client.delete(f'/api/v1/cart/items/{self.line_id}/')
        self.assertEqual(resp.status_code, 404)

    def test_update_another_customers_line_404(self):
        self.authenticate(self.client, self.other_customer)
        resp = self.client.patch(
            f'/api/v1/cart/items/{self.line_id}/', {'quantity': 9}, format='json'
        )
        self.assertEqual(resp.status_code, 404)

    def test_clear_cart(self):
        resp = self.client.delete('/api/v1/cart/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['summary']['item_count'], 0)
        self.assertIsNone(resp.data['restaurant'])


@override_settings(**TEST_SETTINGS)
class CartIssueFlagsTests(CartTestMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = cls.make_customer('flag')
        cls.restaurant = cls.make_restaurant('flag')
        cls.category = cls.make_category(cls.restaurant, 'mains', 3)
        cls.item = cls.make_item(cls.restaurant, 'pie', cls.category, price='10.00')
        cls.unavailable_item = cls.make_item(cls.restaurant, 'gone', cls.category, price='1.00', is_available=False)
        cls.inactive_restaurant = cls.make_restaurant('flag2', is_active=False)
        cls.inactive_category = cls.make_category(cls.inactive_restaurant, 'mains', 3)
        cls.inactive_item = cls.make_item(cls.inactive_restaurant, 'stale', cls.inactive_category, price='1.00')

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.client, self.customer)

    def test_price_changed_flag_and_confirmation_flow(self):
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 1}, format='json')
        resp = self.client.get('/api/v1/cart/')
        self.assertFalse(resp.data['requires_price_confirmation'])

        # Change the menu item price
        self.item.price = Decimal('12.00')
        self.item.save()
        resp = self.client.get('/api/v1/cart/')
        self.assertTrue(resp.data['requires_price_confirmation'])
        line = resp.data['items'][0]
        self.assertTrue(line['price_changed'])
        self.assertEqual(line['unit_price'], '12.00')
        self.assertEqual(line['added_price'], '10.00')

        # Checkout without acceptance -> 409 price_changed
        resp = self.client.post('/api/v1/cart/checkout/', {}, format='json')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data['code'], 'price_changed')

        # Checkout with acceptance -> success
        resp = self.client.post('/api/v1/cart/checkout/', {'accept_price_changes': True}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Order.objects.count(), 1)

    def test_unavailable_item_blocks_checkout(self):
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 1}, format='json')
        # mark the item unavailable after it was added
        self.item.is_available = False
        self.item.save()
        resp = self.client.get('/api/v1/cart/')
        self.assertFalse(resp.data['can_checkout'])
        unavailable = [i for i in resp.data['issues'] if i['code'] == 'item_unavailable']
        self.assertEqual(len(unavailable), 1)
        line_unavail = [i for i in resp.data['items'] if not i['is_available']]
        self.assertEqual(len(line_unavail), 1)

        resp = self.client.post('/api/v1/cart/checkout/', {}, format='json')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data['code'], 'cart_has_issues')

    def test_inactive_restaurant_blocks_checkout(self):
        self.client.post(
            '/api/v1/cart/items/',
            {'menu_item': str(self.item.id), 'quantity': 1},
            format='json',
        )
        self.restaurant.is_active = False
        self.restaurant.save()
        resp = self.client.get('/api/v1/cart/')
        self.assertFalse(resp.data['can_checkout'])
        self.assertTrue(any(i['code'] == 'restaurant_inactive' for i in resp.data['issues']))
        resp = self.client.post('/api/v1/cart/checkout/', {}, format='json')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data['code'], 'cart_has_issues')

    def test_deleted_menu_item_removed_from_cart(self):
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 1}, format='json')
        self.item.delete()
        resp = self.client.get('/api/v1/cart/')
        self.assertEqual(len(resp.data['items']), 0)
        self.assertEqual(resp.data['summary']['item_count'], 0)
        self.assertIsNone(resp.data['restaurant'])


@override_settings(**TEST_SETTINGS)
class CartCheckoutTests(CartTestMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = cls.make_customer('co')
        cls.restaurant = cls.make_restaurant('co')
        cls.category = cls.make_category(cls.restaurant, 'mains', 3)
        cls.item = cls.make_item(cls.restaurant, 'pie', cls.category, prep_time=5, price='10.00')
        cls.item2 = cls.make_item(cls.restaurant, 'cake', cls.category, prep_time=3, price='5.00')

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.client, self.customer)

    def test_checkout_creates_order_and_freezes_cart(self):
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 2}, format='json')
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item2.id), 'quantity': 1}, format='json')
        resp = self.client.post('/api/v1/cart/checkout/', {}, format='json')
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.get(pk=resp.data['id'])
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.restaurant, self.restaurant)
        self.assertFalse(order.is_indoor)
        self.assertEqual(order.order_items.count(), 2)
        pie = order.order_items.get(menu_item=self.item)
        self.assertEqual(pie.quantity, 2)
        self.assertEqual(pie.unit_price, Decimal('10.00'))
        cake = order.order_items.get(menu_item=self.item2)
        self.assertEqual(cake.unit_price, Decimal('5.00'))
        # cart frozen
        cart = Cart.objects.get(customer=self.customer, status=Cart.Status.CHECKED_OUT)
        self.assertEqual(cart.order, order)
        self.assertIsNotNone(cart.checked_out_at)
        # GET cart now returns a fresh empty cart
        get_resp = self.client.get('/api/v1/cart/')
        self.assertEqual(get_resp.data['status'], 'active')
        self.assertEqual(len(get_resp.data['items']), 0)
        self.assertIsNone(get_resp.data['restaurant'])

    def test_double_checkout_returns_one_order(self):
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 1}, format='json')
        resp1 = self.client.post('/api/v1/cart/checkout/', {}, format='json')
        self.assertEqual(resp1.status_code, 201)
        resp2 = self.client.post('/api/v1/cart/checkout/', {}, format='json')
        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(Order.objects.count(), 1)

    def test_empty_cart_checkout_400(self):
        resp = self.client.post('/api/v1/cart/checkout/', {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('cart', resp.data)

    def test_checkout_atomic_rollback_on_issue(self):
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 1}, format='json')
        # make item unavailable then checkout
        self.item.is_available = False
        self.item.save()
        resp = self.client.post('/api/v1/cart/checkout/', {}, format='json')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(Order.objects.count(), 0)
        # cart still active (not frozen)
        self.assertTrue(Cart.objects.filter(customer=self.customer, status=Cart.Status.ACTIVE).exists())


@override_settings(**TEST_SETTINGS)
class CartIntegrationTests(CartTestMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = cls.make_customer('int')
        cls.other_customer = cls.make_customer('int2')
        cls.restaurant = cls.make_restaurant('int')
        cls.category = cls.make_category(cls.restaurant, 'mains', 3)
        cls.item = cls.make_item(cls.restaurant, 'pie', cls.category, prep_time=5, price='10.00')

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.client, self.customer)

    def test_order_appears_in_customer_history(self):
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 2}, format='json')
        self.client.post('/api/v1/cart/checkout/', {}, format='json')
        resp = self.client.get('/api/v1/orders/customers/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 1)
        self.assertEqual(resp.data['results'][0]['customer'], self.customer.id)

    def test_other_customer_does_not_see_order(self):
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 1}, format='json')
        self.client.post('/api/v1/cart/checkout/', {}, format='json')
        self.authenticate(self.client, self.other_customer)
        resp = self.client.get('/api/v1/orders/customers/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 0)

    def test_order_appears_in_restaurant_kitchen_queue_with_priority(self):
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 1}, format='json')
        self.client.post('/api/v1/cart/checkout/', {}, format='json')
        self.authenticate(self.client, self.restaurant.user)
        resp = self.client.get('/api/v1/orders/filtered/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 1)
        self.assertIn('priority_score', resp.data['results'][0])


@override_settings(**TEST_SETTINGS)
class CartQueryCountTests(CartTestMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = cls.make_customer('qc')
        cls.restaurant = cls.make_restaurant('qc')
        cls.category = cls.make_category(cls.restaurant, 'mains', 3)
        cls.item = cls.make_item(cls.restaurant, 'pie', cls.category, price='10.00')

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.client, self.customer)

    def test_get_cart_query_count_one_line(self):
        self.client.post('/api/v1/cart/items/', {'menu_item': str(self.item.id), 'quantity': 1}, format='json')
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get('/api/v1/cart/')
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(ctx.captured_queries), 4, f'{len(ctx.captured_queries)} queries')

    def test_get_cart_query_count_thirteen_lines(self):
        for i in range(13):
            it = MenuItem.objects.create(
                restaurant=self.restaurant,
                name=f'it{i}',
                category=self.category,
                prep_time=1,
                price='1.00',
            )
            self.client.post('/api/v1/cart/items/', {'menu_item': str(it.id), 'quantity': 1}, format='json')
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get('/api/v1/cart/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['summary']['distinct_items'], 13)
        self.assertLessEqual(len(ctx.captured_queries), 4, f'{len(ctx.captured_queries)} queries')


@override_settings(**TEST_SETTINGS)
@override_settings(**TEST_SETTINGS)
class CartConcurrencyTests(CartTestMixin, TestCase):
    def setUp(self):
        self.customer = self.make_customer('conc')
        self.restaurant = self.make_restaurant('conc')
        self.category = self.make_category(self.restaurant, 'mains', 3)
        self.item = self.make_item(self.restaurant, 'pie', self.category, price='10.00')
        self.cart = Cart.objects.create(customer=self.customer, restaurant=self.restaurant)
        CartItem.objects.create(
            cart=self.cart, menu_item=self.item, quantity=1, added_price=Decimal('10.00')
        )

    def test_sequential_double_checkout_one_order(self):
        CartService.checkout(self.customer, accept_price_changes=True)
        with self.assertRaises(CartConflict):
            CartService.checkout(self.customer, accept_price_changes=True)
        self.assertEqual(Order.objects.count(), 1)


@override_settings(**TEST_SETTINGS)
class CartExpiryTests(CartTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = cls.make_customer('exp')
        cls.restaurant = cls.make_restaurant('exp')
        cls.category = cls.make_category(cls.restaurant, 'mains', 3)
        cls.item = cls.make_item(cls.restaurant, 'pie', cls.category, price='10.00')

    def test_expire_carts_marks_idle_carts_abandoned(self):
        old_cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(cart=old_cart, menu_item=self.item, quantity=1, added_price=Decimal('10.00'))
        Cart.objects.filter(pk=old_cart.pk).update(updated_at=timezone.now() - timedelta(days=40))
        Cart.objects.create(customer=self.make_customer('exp2'))

        count = CartService.expire_carts(days=30)
        self.assertEqual(count, 1)
        old_cart.refresh_from_db()
        self.assertEqual(old_cart.status, Cart.Status.ABANDONED)
        self.assertTrue(Cart.objects.filter(status=Cart.Status.ACTIVE).exists())

    def test_expire_carts_command(self):
        from django.core.management import call_command
        import io
        old_cart = Cart.objects.create(customer=self.customer)
        Cart.objects.filter(pk=old_cart.pk).update(updated_at=timezone.now() - timedelta(days=40))
        out = io.StringIO()
        call_command('expire_carts', '--days', '30', stdout=out)
        old_cart.refresh_from_db()
        self.assertEqual(old_cart.status, Cart.Status.ABANDONED)
        self.assertIn('abandoned', out.getvalue())
