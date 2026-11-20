"""CustomerOrderService: delivery orders placed by customers."""
from decimal import Decimal

from django.http import Http404
from rest_framework.exceptions import ValidationError

from apps.orders.services import CustomerOrderService
from apps.orders.tests.base import OrdersTestCase, create_customer, make_order, reload


def payload(*pairs):
    return {'order_items': [{'menu_item': m, 'quantity': q} for m, q in pairs]}


class CreateTests(OrdersTestCase):

    def setUp(self):
        self.customer = create_customer()

    def test_creates_delivery_order(self):
        order = CustomerOrderService.create_order(
            self.customer, self.restaurant, payload((self.burger, 2)),
        )
        self.assertFalse(order.is_indoor)
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.created_by, self.customer)
        self.assertEqual(order.status, 'pending')
        self.assertFalse(order.special_flag)
        self.assertEqual(order.order_items.get().unit_price, Decimal('9.00'))
        self.assertGreater(order.priority_score, 0)

    def test_inactive_restaurant_is_rejected(self):
        self.restaurant.is_active = False
        self.restaurant.save()
        with self.assertRaises(ValidationError):
            CustomerOrderService.create_order(self.customer, self.restaurant, payload((self.burger, 1)))

    def test_delivery_orders_get_a_batch_number(self):
        """
        Delivery orders should get a batch_number assigned at creation time,
        matching the behavior of dine-in orders via OrderService.create_order.
        """
        order = CustomerOrderService.create_order(
            self.customer, self.restaurant, payload((self.burger, 1)),
        )
        self.assertEqual(order.batch_number, 1)


class OwnershipTests(OrdersTestCase):

    def setUp(self):
        self.customer = create_customer('c1')
        self.stranger = create_customer('c2')
        self.order = make_order(self.restaurant, [(self.fries, 1)], is_indoor=False, customer=self.customer)

    def test_owner_can_fetch(self):
        self.assertEqual(CustomerOrderService.get_owned_order(self.customer, self.order.pk), self.order)

    def test_other_customer_gets_404(self):
        with self.assertRaises(Http404):
            CustomerOrderService.get_owned_order(self.stranger, self.order.pk)

    def test_dine_in_orders_are_not_visible_to_customers(self):
        dine_in = make_order(self.restaurant, customer=self.customer, is_indoor=True)
        with self.assertRaises(Http404):
            CustomerOrderService.get_owned_order(self.customer, dine_in.pk)

    def test_list_only_returns_my_delivery_orders(self):
        make_order(self.restaurant, customer=self.stranger, is_indoor=False)
        make_order(self.restaurant, customer=self.customer, is_indoor=True)
        mine = list(CustomerOrderService.get_customer_orders_qs(self.customer))
        self.assertEqual(mine, [self.order])


class UpdateAndCancelTests(OrdersTestCase):

    def setUp(self):
        self.customer = create_customer()

    def delivery(self, **kw):
        return make_order(self.restaurant, [(self.fries, 1)], is_indoor=False,
                          customer=self.customer, **kw)

    def test_update_replaces_items_and_rescores(self):
        order = self.delivery()
        before = order.priority_score
        CustomerOrderService.update_order(order, payload((self.steak, 4)))
        fresh = reload(order)
        self.assertEqual(fresh.order_items.get().menu_item, self.steak)
        self.assertLess(fresh.priority_score, before)

    def test_update_is_rejected_once_finished(self):
        for status in ('done', 'cancelled'):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                CustomerOrderService.update_order(self.delivery(status=status), payload((self.steak, 1)))

    def test_cancel(self):
        order = self.delivery()
        CustomerOrderService.cancel_order(order)
        self.assertEqual(reload(order).status, 'cancelled')

    def test_cannot_cancel_twice_or_after_done(self):
        for status in ('cancelled', 'done'):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                CustomerOrderService.cancel_order(self.delivery(status=status))
