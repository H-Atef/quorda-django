"""
PriorityCalculator: score = w_time*time + w_qty*qty + w_cat*category

    time_score     = min(2 / (total_prep_minutes + 1), 1)
    quantity_score = min(2 / (total_quantity + 1), 1)
    category_score = (highest category priority - 1) / 4

Higher score = cooked sooner.
"""
from types import SimpleNamespace as NS

from apps.orders.helpers.priority_calculator import PriorityCalculator
from apps.orders.models import OrderItem
from apps.orders.tests.base import OrdersTestCase, make_order
from apps.restaurants.models import RestaurantCalculationParams


class ComputeScoreTests(OrdersTestCase):

    def score(self, items):
        return PriorityCalculator.compute_score(make_order(self.restaurant, items))

    def test_empty_order_scores_zero(self):
        self.assertEqual(self.score([]), 0.0)

    def test_best_possible_order_scores_one(self):
        # 1 fries: time 1 min, qty 1, priority 5 -> 0.4*1 + 0.4*1 + 0.2*1
        self.assertAlmostEqual(self.score([(self.fries, 1)]), 1.0)

    def test_known_value(self):
        # 1 burger: total_time 10 -> 2/11 ; qty 1 -> 1 ; priority 3 -> 0.5
        expected = 0.4 * (2 / 11) + 0.4 * 1 + 0.2 * 0.5
        self.assertAlmostEqual(self.score([(self.burger, 1)]), expected)

    def test_scores_are_bounded_between_zero_and_one(self):
        for items in ([(self.fries, 1)], [(self.steak, 50)], [(self.burger, 3), (self.fries, 2)]):
            with self.subTest(items=[(i.name, q) for i, q in items]):
                self.assertTrue(0.0 <= self.score(items) <= 1.0)

    def test_quicker_order_ranks_higher(self):
        self.assertGreater(self.score([(self.fries, 1)]), self.score([(self.steak, 1)]))

    def test_more_quantity_lowers_score(self):
        self.assertGreater(self.score([(self.burger, 1)]), self.score([(self.burger, 5)]))

    def test_category_uses_highest_priority_in_the_order(self):
        mixed = self.score([(self.steak, 1), (self.fries, 1)])
        low_only = self.score([(self.steak, 2)])
        self.assertGreater(mixed, low_only)

    def test_items_without_menu_item_are_ignored(self):
        order = make_order(self.restaurant, [(self.fries, 1)])
        OrderItem.objects.create(order=order, menu_item=None, quantity=9)
        self.assertAlmostEqual(PriorityCalculator.compute_score(order), 1.0)

    def test_order_with_only_deleted_items_scores_zero(self):
        order = make_order(self.restaurant)
        OrderItem.objects.create(order=order, menu_item=None, quantity=3)
        self.assertEqual(PriorityCalculator.compute_score(order), 0.0)

    def test_item_without_category_gets_zero_category_score(self):
        self.fries.category = None
        self.fries.save()
        # time 1.0 and qty 1.0 still count, category part is 0
        self.assertAlmostEqual(self.score([(self.fries, 1)]), 0.4 + 0.4)

    def test_preloaded_items_skip_the_query(self):
        order = make_order(self.restaurant, [(self.fries, 1)])
        items = list(order.order_items.select_related('menu_item__category'))
        order.restaurant  # warm the FK cache
        PriorityCalculator._get_params(order.restaurant)  # warm calculation_params cache
        with self.assertNumQueries(0):
            PriorityCalculator.compute_score(order, items=items)


class WeightsTests(OrdersTestCase):

    def test_default_weights_sum_to_one(self):
        total = (PriorityCalculator.TIME_WEIGHT + PriorityCalculator.QUANTITY_WEIGHT
                 + PriorityCalculator.CATEGORY_WEIGHT)
        self.assertAlmostEqual(total, 1.0)

    def test_defaults_used_when_restaurant_has_no_params(self):
        params = PriorityCalculator._get_params(self.restaurant)
        self.assertEqual(params, {'time_weight': 0.4, 'quantity_weight': 0.4, 'category_weight': 0.2})

    def test_defaults_used_when_restaurant_is_none(self):
        self.assertEqual(PriorityCalculator._get_params(None)['time_weight'], 0.4)

    def test_custom_weights_change_the_score(self):
        RestaurantCalculationParams.objects.create(
            restaurant=self.restaurant, time_weight=0.0, quantity_weight=0.0, category_weight=1.0,
        )
        order = make_order(self.restaurant, [(self.burger, 1)])
        order = type(order).objects.get(pk=order.pk)  # drop cached relations
        self.assertAlmostEqual(PriorityCalculator.compute_score(order), 0.5)  # category only

    def test_other_restaurants_params_do_not_apply(self):
        RestaurantCalculationParams.objects.create(
            restaurant=self.other_restaurant, time_weight=0.0, quantity_weight=0.0, category_weight=1.0,
        )
        order = make_order(self.restaurant, [(self.burger, 1)])
        self.assertAlmostEqual(
            PriorityCalculator.compute_score(order),
            0.4 * (2 / 11) + 0.4 + 0.2 * 0.5,
        )


class RecalculateTests(OrdersTestCase):

    def test_recalculate_persists_the_score(self):
        order = make_order(self.restaurant, [(self.fries, 1)], score=0.0)
        order.recalculate_priority_score()
        order.refresh_from_db()
        self.assertAlmostEqual(order.priority_score, 1.0)

    def test_pure_scoring_works_on_plain_objects(self):
        """compute_score only needs duck-typed items (the benchmark relies on this)."""
        item = NS(menu_item=NS(prep_time=1, category=NS(priority=5)), quantity=1)
        self.assertAlmostEqual(
            PriorityCalculator.compute_score(NS(restaurant=None), items=[item]), 1.0,
        )
