"""Order / OrderItem computed properties."""
from decimal import Decimal

from apps.orders.models import OrderItem
from apps.orders.tests.base import OrdersTestCase, make_order


class OrderPropertiesTests(OrdersTestCase):

    def setUp(self):
        self.order = make_order(self.restaurant, [(self.fries, 2), (self.burger, 3)])

    def test_total_quantity(self):
        self.assertEqual(self.order.total_quantity, 5)

    def test_total_prep_time_is_prep_time_times_quantity(self):
        self.assertEqual(self.order.total_prep_time, 2 * 1 + 3 * 10)

    def test_total_cost(self):
        self.assertAlmostEqual(self.order.total_cost, 2 * 2.00 + 3 * 9.00)

    def test_empty_order_totals_are_zero(self):
        empty = make_order(self.restaurant)
        self.assertEqual((empty.total_quantity, empty.total_prep_time, empty.total_cost), (0, 0, 0))

    def test_cost_uses_price_snapshot_not_current_menu_price(self):
        """Changing the menu price later must not rewrite past orders."""
        self.burger.price = Decimal('99.00')
        self.burger.save()
        self.assertAlmostEqual(self.order.total_cost, 2 * 2.00 + 3 * 9.00)

    def test_cost_falls_back_to_menu_price_without_snapshot(self):
        OrderItem.objects.filter(order=self.order).update(unit_price=None)
        self.assertAlmostEqual(self.order.total_cost, 2 * 2.00 + 3 * 9.00)

    def test_deleting_menu_item_keeps_order_item(self):
        """menu_item is SET_NULL: the line survives and contributes 0 prep time."""
        self.burger.delete()
        self.assertEqual(self.order.order_items.count(), 2)
        self.assertEqual(self.order.total_prep_time, 2 * 1)
        self.assertAlmostEqual(self.order.total_cost, 2 * 2.00 + 3 * 9.00)  # snapshot price

    def test_defaults(self):
        self.assertEqual(self.order.status, 'pending')
        self.assertTrue(self.order.is_indoor)
        self.assertFalse(self.order.special_flag)
        self.assertIsNone(self.order.batch_number)

    def test_str_mentions_restaurant_and_status(self):
        self.assertIn('A', str(self.order))
        self.assertIn('pending', str(self.order))


class OrderItemPropertiesTests(OrdersTestCase):

    def test_item_totals(self):
        order = make_order(self.restaurant, [(self.steak, 2)])
        item = order.order_items.get()
        self.assertEqual(item.total_prep_time, 40)
        self.assertAlmostEqual(item.total_price, 36.0)

    def test_item_without_menu_item(self):
        order = make_order(self.restaurant, [(self.steak, 2)])
        item = order.order_items.get()
        item.menu_item = None
        self.assertEqual(item.total_prep_time, 0)
        self.assertIn('deleted item', str(item))
