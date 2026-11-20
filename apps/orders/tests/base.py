"""
Shared fixtures for the orders test-suite.

Everything here is deliberately tiny and explicit so a test reads top-down:

    order = make_order(self.restaurant, [(self.burger, 2)], status='pending')

Two restaurants (A and B) are created so tests can prove that data never
leaks across tenants.

Run the whole suite (in-memory SQLite, no Postgres needed):

    python -m django test apps/orders/tests -t . --settings=config.settings.test
    (or: pytest apps/orders/tests  with DJANGO_SETTINGS_MODULE=config.settings.test)
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.orders.models import Order, OrderItem
from apps.restaurants.models import Category, Criteria, MenuItem
from apps.users.models import CashierProfile, RestaurantProfile, User

PASSWORD = 'pass12345'


# --------------------------------------------------------------------------
# Factories
# --------------------------------------------------------------------------
def create_restaurant(name):
    """Return (owner_user, RestaurantProfile)."""
    owner = User.objects.create_user(
        username=f'{name}_owner', email=f'{name}_owner@example.com',
        password=PASSWORD, role='restaurant',
    )
    restaurant = RestaurantProfile.objects.create(user=owner, restaurant_name=name)
    return owner, restaurant


def create_cashier(restaurant, username='cashier', can_set_vip=False, is_active=True):
    """Return the cashier's User, linked to `restaurant`."""
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com',
        password=PASSWORD, role='cashier',
    )
    CashierProfile.objects.create(
        user=user, restaurant=restaurant, can_set_vip=can_set_vip, is_active=is_active,
    )
    return user


def create_customer(username='customer'):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com',
        password=PASSWORD, role='customer',
    )


def create_menu(restaurant):
    """
    Three items with very different scores:

        fries : priority 5, prep  1 min, $2   (fast + high priority -> best score)
        burger: priority 3, prep 10 min, $9
        steak : priority 1, prep 20 min, $18  (slow + low priority  -> worst score)
    """
    cats = {
        p: Category.objects.create(restaurant=restaurant, name=f'cat{p}', priority=p)
        for p in (1, 3, 5)
    }
    make = lambda name, cat, prep, price: MenuItem.objects.create(  # noqa: E731
        restaurant=restaurant, name=name, category=cats[cat],
        prep_time=prep, price=Decimal(price),
    )
    return {
        'fries': make('Fries', 5, 1, '2.00'),
        'burger': make('Burger', 3, 10, '9.00'),
        'steak': make('Steak', 1, 20, '18.00'),
    }


def make_order(restaurant, items=(), *, status='pending', special_flag=False,
               is_indoor=True, customer=None, batch_number=None,
               created_minutes_ago=None, score=None):
    """
    Create an order with items and return it.

    items                 : iterable of (MenuItem, quantity)
    created_minutes_ago   : back-date created_at (controls "oldest first")
    score                 : force priority_score (otherwise it is computed)
    """
    order = Order.objects.create(
        restaurant=restaurant, status=status, special_flag=special_flag,
        is_indoor=is_indoor, customer=customer, batch_number=batch_number,
    )
    for menu_item, qty in items:
        OrderItem.objects.create(
            order=order, menu_item=menu_item, quantity=qty, unit_price=menu_item.price,
        )
    if items:
        order.recalculate_priority_score()

    overrides = {}
    if created_minutes_ago is not None:
        overrides['created_at'] = timezone.now() - timedelta(minutes=created_minutes_ago)
    if score is not None:
        overrides['priority_score'] = score
    if overrides:  # queryset.update() bypasses auto_now_add
        Order.objects.filter(pk=order.pk).update(**overrides)
        order.refresh_from_db()
    return order


def reload(order):
    return Order.objects.get(pk=order.pk)


# --------------------------------------------------------------------------
# Base classes
# --------------------------------------------------------------------------
class OrdersFixtureMixin:
    """Creates restaurants A and B (+ menu) once per test class."""

    @classmethod
    def setUpTestData(cls):
        cls.owner, cls.restaurant = create_restaurant('A')
        cls.other_owner, cls.other_restaurant = create_restaurant('B')
        cls.menu = create_menu(cls.restaurant)
        cls.other_menu = create_menu(cls.other_restaurant)
        cls.fries, cls.burger, cls.steak = (cls.menu[k] for k in ('fries', 'burger', 'steak'))


class OrdersTestCase(OrdersFixtureMixin, TestCase):
    """Service / helper level tests (no HTTP)."""


class OrdersAPITestCase(OrdersFixtureMixin, APITestCase):
    """HTTP level tests. `self.client` is authenticated as the owner of A."""

    def setUp(self):
        self.client.force_authenticate(self.owner)

    def as_user(self, user):
        """Return a fresh client authenticated as `user` (None = anonymous)."""
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    @staticmethod
    def ids(response):
        """Order ids of a paginated list response, in the returned order."""
        return [row['id'] for row in response.data['results']]

    @staticmethod
    def pk(order):
        return str(order.pk)
