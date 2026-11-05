from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.orders.helpers.priority_calculator import PriorityCalculator
from apps.orders.helpers.simple_order_detector import SimpleOrderDetector
from apps.orders.models import Order, OrderItem
from apps.orders.serializers import OrderWriteSerializer
from apps.restaurants.models import Category, Criteria, MenuItem
from apps.users.models import RestaurantProfile, User


# Test settings: in-memory SQLite database (faster and doesn't touch real data),
# and a lightweight password hasher (MD5) so creating users in tests isn't slow.
TEST_SETTINGS = {
    'DATABASES': {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    'PASSWORD_HASHERS': ['django.contrib.auth.hashers.MD5PasswordHasher'],
}


class OrderTestMixin:
    """
    Helper functions that build test data: restaurant, category, item, order.
    All tests below use these instead of duplicating the same code.
    """

    @classmethod
    def make_restaurant(cls, suffix='r1'):
        # Creates a user with the 'restaurant' role and a restaurant profile linked to it.
        # The suffix makes each restaurant's name different so the username stays unique.
        user = User.objects.create_user(
            username=f'rest_{suffix}',
            password='pass12345',
            role='restaurant',
            email=f'rest_{suffix}@example.com',
        )
        return RestaurantProfile.objects.create(
            user=user,
            restaurant_name=f'Restaurant {suffix}',
            address='123 Test St',
        )

    @classmethod
    def make_category(cls, restaurant, name, priority):
        # A category with a priority (1 = normal ... 5 = highest).
        return Category.objects.create(restaurant=restaurant, name=name, priority=priority)

    @classmethod
    def make_item(cls, restaurant, name, category, prep_time, price='1.00'):
        # A menu item with a prep time (prep_time in minutes) and a price.
        return MenuItem.objects.create(
            restaurant=restaurant,
            name=name,
            category=category,
            prep_time=prep_time,
            price=Decimal(price),
            is_available=True,
        )

    @classmethod
    def make_order(cls, restaurant, status=Order.Status.PENDING, special=False, created_at=None):
        # Creates an empty order. If created_at is given, we update it directly
        # with update() because the auto_now_add field can't be set at creation time.
        order = Order.objects.create(
            restaurant=restaurant,
            is_indoor=True,
            status=status,
            special_flag=special,
        )
        if created_at is not None:
            Order.objects.filter(pk=order.pk).update(created_at=created_at)
            order.refresh_from_db()
        return order

    @classmethod
    def add_item(cls, order, menu_item, quantity):
        # Adds an item with a quantity to the order.
        return OrderItem.objects.create(order=order, menu_item=menu_item, quantity=quantity)


@override_settings(**TEST_SETTINGS)
class PriorityCalculatorTests(OrderTestMixin, TestCase):
    """Tests for score computation (PriorityCalculator) without any API."""

    @classmethod
    def setUpTestData(cls):
        # Runs once for the whole class: one restaurant shared across tests.
        cls.restaurant = cls.make_restaurant('score')

    def _score_for(self, category_priority, prep_time, quantity):
        # Helper: builds an order with a single item matching these specs and returns its score.
        # Names include the numbers so they don't repeat and break uniqueness.
        cat = self.make_category(self.restaurant, f'c{category_priority}{prep_time}{quantity}', category_priority)
        item = self.make_item(self.restaurant, f'm{category_priority}{prep_time}{quantity}', cat, prep_time=prep_time)
        order = self.make_order(self.restaurant)
        self.add_item(order, item, quantity)
        return PriorityCalculator.compute_score(order)

    def test_scale_lowest_category_never_outranks_higher_with_equal_prep(self):
        """
        Goal: ensure category affects the score without overpowering time and quantity.
        Verifies two things:
          1) an order with category priority 1 must not score higher than an order with
             priority 5 when prep time and quantity are equal.
          2) each of the three components (time, quantity, category) must be between 0 and 1.
        Note: the second part recomputes the time and quantity formula inside the test itself,
        so if you change the formula in PriorityCalculator this test won't notice.
        """
        # Req 1: category matters but cannot swamp time/quantity; each component is in 0..1.
        low = self._score_for(category_priority=1, prep_time=5, quantity=1)
        high = self._score_for(category_priority=5, prep_time=5, quantity=1)
        self.assertLessEqual(low, high)

        # Build a new order and compute the three components manually to verify they're in 0..1.
        cat = self.make_category(self.restaurant, 'components', 5)
        item = self.make_item(self.restaurant, 'components-item', cat, prep_time=1)
        order = self.make_order(self.restaurant)
        self.add_item(order, item, 1)
        items = list(order.order_items.select_related('menu_item__category'))
        time_score = min(2.0 / (sum(i.menu_item.prep_time * i.quantity for i in items) + 1), 1.0)
        qty_score = min(2.0 / (sum(i.quantity for i in items) + 1), 1.0)
        cat_score = PriorityCalculator._category_score(items)
        for value in (time_score, qty_score, cat_score):
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_quantity_independence_for_category_score(self):
        """
        Goal: the category score must not be affected by quantity (this was the old bug:
        quantity was multiplied into the boost, so bigger orders got a higher score).
        An order with one item and an order with 10 of the same category (priority 5):
        both must get exactly the same category score of 1.0.
        """
        cat = self.make_category(self.restaurant, 'highcat', 5)
        small_item = self.make_item(self.restaurant, 'small', cat, prep_time=5)
        large_item = self.make_item(self.restaurant, 'large', cat, prep_time=5)
        small = self.make_order(self.restaurant)
        large = self.make_order(self.restaurant)
        self.add_item(small, small_item, 1)    # quantity 1
        self.add_item(large, large_item, 10)   # quantity 10
        small_items = list(small.order_items.select_related('menu_item__category'))
        large_items = list(large.order_items.select_related('menu_item__category'))
        # (5-1)/4 = 1.0 for both, regardless of quantity.
        self.assertEqual(PriorityCalculator._category_score(small_items), 1.0)
        self.assertEqual(PriorityCalculator._category_score(large_items), 1.0)

    def test_small_quick_order_outranks_large_slow_same_category(self):
        """
        Goal: the project's core behavior: small quick orders should outrank large slow ones.
        Same category for both, so the difference comes only from time and quantity:
          quick: 1-minute item × 1 unit
          slow: 20-minute item × 8 units
        The quick order's score must be higher.
        """
        cat = self.make_category(self.restaurant, 'same', 3)
        quick_item = self.make_item(self.restaurant, 'quick', cat, prep_time=1)
        slow_item = self.make_item(self.restaurant, 'slow', cat, prep_time=20)
        quick = self.make_order(self.restaurant)
        slow = self.make_order(self.restaurant)
        self.add_item(quick, quick_item, 1)
        self.add_item(slow, slow_item, 8)
        self.assertGreater(PriorityCalculator.compute_score(quick), PriorityCalculator.compute_score(slow))

    def test_null_menu_item_does_not_raise(self):
        """
        Goal: if a menu item was deleted (menu_item is None), the system shouldn't crash.
        The order contains:
          - a valid item: 5 minutes × 2 units
          - a deleted item (None) × 3 units (must be ignored in calculations)
        We verify that:
          - total_prep_time = 10 (the deleted item isn't counted)
          - total_cost = 2.0 (2 × price 1.00)
          - compute_score works and returns a positive number
          - SimpleOrderDetector also doesn't crash and returns a result.
        """
        cat = self.make_category(self.restaurant, 'nullcat', 4)
        valid = self.make_item(self.restaurant, 'valid', cat, prep_time=5)
        order = self.make_order(self.restaurant)
        self.add_item(order, valid, 2)
        OrderItem.objects.create(order=order, menu_item=None, quantity=3)  # deleted item
        order.refresh_from_db()
        self.assertEqual(order.total_prep_time, 10)
        self.assertEqual(order.total_cost, 2.0)
        score = PriorityCalculator.compute_score(order)
        self.assertGreater(score, 0.0)
        # SimpleOrderDetector null safety
        criteria = Criteria.objects.create(restaurant=self.restaurant, max_quantity=10, min_category_priority=4)
        result = SimpleOrderDetector.detect([order], criteria)
        self.assertEqual(len(result), 1)


@override_settings(**TEST_SETTINGS)
class WindowedOrderAPITests(OrderTestMixin, APITestCase):
    """API tests for the orders endpoints (Windowed endpoints) using a restaurant user."""

    @classmethod
    def setUpTestData(cls):
        # One restaurant, category, and item shared across all tests in the class.
        cls.restaurant = cls.make_restaurant('api')
        cls.category = cls.make_category(cls.restaurant, 'main', 3)
        cls.menu_item = cls.make_item(cls.restaurant, 'item', cls.category, prep_time=5)

    def setUp(self):
        # Before each test: an API client authenticated as the restaurant owner (no token).
        self.client = APIClient()
        self.client.force_authenticate(user=self.restaurant.user)

    def _create_with_status(self, status, minutes_ago):
        # An order with a given status created X minutes ago, containing one item. Used to set up the time ordering.
        order = self.make_order(self.restaurant, status=status, created_at=timezone.now() - timedelta(minutes=minutes_ago))
        self.add_item(order, self.menu_item, 1)
        return order

    def test_windowed_excludes_done_cancelled_by_default_and_respects_status(self):
        """
        Goal: Fix 4: the window should only show active orders.
        Create 4 orders (pending, preparing, done, cancelled) and verify:
          1) without a filter: only pending and preparing are returned.
          2) with ?status=pending,done: only the requested statuses are returned (preparing disappears).
        """
        pending = self._create_with_status(Order.Status.PENDING, 30)
        preparing = self._create_with_status(Order.Status.PREPARING, 20)
        self._create_with_status(Order.Status.DONE, 10)
        self._create_with_status(Order.Status.CANCELLED, 5)

        # 1) Default behavior
        resp = self.client.get('/api/v1/orders/windowed/', {'window_size': 10})
        self.assertEqual(resp.status_code, 200)
        ids = [o['id'] for o in resp.data]
        self.assertEqual(set(ids), {str(pending.id), str(preparing.id)})

        # 2) With an explicit status filter
        resp = self.client.get('/api/v1/orders/windowed/', {'window_size': 10, 'status': 'pending,done'})
        self.assertEqual(resp.status_code, 200)
        ids = [o['id'] for o in resp.data]
        self.assertIn(str(pending.id), ids)
        self.assertTrue(any(Order.objects.get(pk=i).status == Order.Status.DONE for i in ids))
        self.assertNotIn(str(preparing.id), ids)

    def test_preparing_orders_stay_before_pending(self):
        """
        Goal: an order currently being prepared (preparing) must not be pushed below a pending order.
        Create 2 pending and 2 preparing orders with different times and verify that:
          - the first two in the result are the preparing ones (oldest first)
          - the pending ones come after them (their relative order depends on score, so we compare without ordering).
        """
        pending_old = self._create_with_status(Order.Status.PENDING, 60)
        pending_new = self._create_with_status(Order.Status.PENDING, 50)
        preparing_new = self._create_with_status(Order.Status.PREPARING, 5)
        preparing_old = self._create_with_status(Order.Status.PREPARING, 40)

        resp = self.client.get('/api/v1/orders/windowed/', {'window_size': 10})
        self.assertEqual(resp.status_code, 200)
        ids = [o['id'] for o in resp.data]
        self.assertEqual(ids[:2], [str(preparing_old.id), str(preparing_new.id)])
        self.assertCountEqual(ids[2:], [str(pending_old.id), str(pending_new.id)])

    def test_normal_windowed_excludes_done_cancelled_and_keeps_preparing_first(self):
        """
        Goal: same rules on the normal orders endpoint (/normal/windowed/):
        done is excluded, and preparing comes before pending.
        Expected result exactly: [preparing, pending].
        """
        pending = self._create_with_status(Order.Status.PENDING, 30)
        preparing = self._create_with_status(Order.Status.PREPARING, 20)
        self._create_with_status(Order.Status.DONE, 10)

        resp = self.client.get('/api/v1/orders/normal/windowed/', {'window_size': 10})
        self.assertEqual(resp.status_code, 200)
        ids = [o['id'] for o in resp.data]
        self.assertEqual(ids, [str(preparing.id), str(pending.id)])

    def test_simple_orders_query_count_bounded(self):
        """
        Goal: Fix 8 (N+1): the simple orders endpoint must not run a query per order.
        Create 20 orders and count the queries executed. If there were an N+1, the count would exceed 20.
        We verify the count is <= 6 (a rough number: auth, criteria, reading orders, etc.).
        """
        Criteria.objects.create(restaurant=self.restaurant, max_quantity=100, min_category_priority=1)
        for i in range(20):
            order = self.make_order(self.restaurant, created_at=timezone.now() - timedelta(minutes=i))
            self.add_item(order, self.menu_item, 1)
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as ctx:   # captures every SQL query executed inside the with block
            resp = self.client.get('/api/v1/orders/simple/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 20)
        self.assertLessEqual(len(ctx.captured_queries), 6)


@override_settings(**TEST_SETTINGS)
class SortingAndSerializerTests(OrderTestMixin, TestCase):
    """Tests for sorting (OrderSorter) and the serializer."""

    @classmethod
    def setUpTestData(cls):
        cls.restaurant = cls.make_restaurant('sort')
        cls.category = cls.make_category(cls.restaurant, 'main', 3)
        cls.item = cls.make_item(cls.restaurant, 'food', cls.category, prep_time=5)

    def test_equal_scores_oldest_first(self):
        """
        Goal: Fix 5 (the tie-break): when two scores are equal, the older one is prepared first.
        Two identical orders (same item and quantity), one of them 5 minutes older.
        We verify that:
          1) the two scores are actually equal.
          2) passing them to the sorter in reverse order [newer, older] returns [older, newer].
        """
        now = timezone.now()
        older = self.make_order(self.restaurant, created_at=now - timedelta(minutes=10))
        newer = self.make_order(self.restaurant, created_at=now - timedelta(minutes=5))
        self.add_item(older, self.item, 1)
        self.add_item(newer, self.item, 1)
        older.recalculate_priority_score()
        newer.recalculate_priority_score()
        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertAlmostEqual(older.priority_score, newer.priority_score, places=9)
        from apps.orders.helpers.order_sorter import OrderSorter
        ordered = OrderSorter.get_normal_orders([newer, older])
        self.assertEqual([o.id for o in ordered], [older.id, newer.id])

    def test_order_write_serializer_rejects_empty_order_items(self):
        """
        Goal: Fix 7: the restaurant serializer must reject an order with no items
        (the customer serializers already rejected it, but the restaurant one didn't).
        We send empty order_items and verify the serializer is not valid
        and the error is shown on the order_items field.
        """
        data = {
            'is_indoor': True,
            'status': Order.Status.PENDING,
            'special_flag': False,
            'order_items': [],
        }
        serializer = OrderWriteSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('order_items', serializer.errors)