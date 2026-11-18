"""
Tests for SimpleOrderDetector.

Run with the in-memory SQLite settings (no Postgres needed):
    python -m django test apps.orders.tests.test_simple_order_detector --settings=config.settings.test
"""

from django.test import TestCase

from apps.orders.helpers.simple_order_detector import SimpleOrderDetector
from apps.orders.models import Order, OrderItem
from apps.restaurants.models import Category, Criteria, MenuItem
from apps.users.models import RestaurantProfile, User


class SimpleOrderDetectorTests(TestCase):
    """Verify detection logic, queryset handling, and query count."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='owner1', email='owner1@example.com',
            password='pass12345', role='restaurant',
        )
        cls.restaurant = RestaurantProfile.objects.create(
            user=cls.owner, restaurant_name='Test Rest', address='123 Test St',
        )
        cls.cat_low = Category.objects.create(restaurant=cls.restaurant, name='Low', priority=1)
        cls.cat_high = Category.objects.create(restaurant=cls.restaurant, name='High', priority=5)
        cls.item_low = MenuItem.objects.create(
            restaurant=cls.restaurant, name='Low Item', category=cls.cat_low,
            price='10.00', prep_time=5,
        )
        cls.item_high = MenuItem.objects.create(
            restaurant=cls.restaurant, name='High Item', category=cls.cat_high,
            price='20.00', prep_time=10,
        )
        cls.item_no_cat = MenuItem.objects.create(
            restaurant=cls.restaurant, name='No Cat Item', category=None,
            price='15.00', prep_time=5,
        )
        cls.criteria = Criteria.objects.create(
            restaurant=cls.restaurant, max_quantity=2, min_category_priority=5,
        )

        # Order 1: Simple (qty=2, max_prio=5) -> SHOULD MATCH
        cls.order1 = Order.objects.create(restaurant=cls.restaurant, status='pending')
        OrderItem.objects.create(order=cls.order1, menu_item=cls.item_high, quantity=2)

        # Order 2: Too many items (qty=6, max_prio=5) -> SHOULD NOT MATCH
        cls.order2 = Order.objects.create(restaurant=cls.restaurant, status='pending')
        OrderItem.objects.create(order=cls.order2, menu_item=cls.item_high, quantity=6)

        # Order 3: Low priority (qty=2, max_prio=1) -> SHOULD NOT MATCH
        cls.order3 = Order.objects.create(restaurant=cls.restaurant, status='pending')
        OrderItem.objects.create(order=cls.order3, menu_item=cls.item_low, quantity=2)

        # Order 4: No items (qty=0, max_prio=0) -> SHOULD NOT MATCH
        cls.order4 = Order.objects.create(restaurant=cls.restaurant, status='pending')

        # Order 5: Items but no category (qty=2, max_prio=0) -> SHOULD NOT MATCH
        cls.order5 = Order.objects.create(restaurant=cls.restaurant, status='pending')
        OrderItem.objects.create(order=cls.order5, menu_item=cls.item_no_cat, quantity=2)

    def test_detect_simple_orders_from_queryset(self):
        """Only the matching order is returned when passing a base QuerySet."""
        result = SimpleOrderDetector.detect(Order.objects.all(), self.criteria)

        self.assertIn(type(result).__name__, ('list', 'QuerySet'))
        result_ids = [o.id for o in result]
        self.assertIn(self.order1.id, result_ids)
        self.assertNotIn(self.order2.id, result_ids)
        self.assertNotIn(self.order3.id, result_ids)
        self.assertNotIn(self.order4.id, result_ids)
        self.assertNotIn(self.order5.id, result_ids)

    def test_detect_with_pre_filtered_queryset(self):
        """A pre-filtered queryset is handled correctly."""
        pre_filtered = Order.objects.filter(id=self.order1.id)
        result = SimpleOrderDetector.detect(pre_filtered, self.criteria)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, self.order1.id)

    def test_no_n_plus_one_queries(self):
        """CRITICAL: detection runs in a single SQL query."""
        with self.assertNumQueries(1):
            list(SimpleOrderDetector.detect(Order.objects.all(), self.criteria))