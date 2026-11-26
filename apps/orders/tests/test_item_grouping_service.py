"""ItemGroupingService: identical items across queued orders, kept in queue order."""
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.orders.models import Order, OrderItem
from apps.orders.serializers import OrderListSerializer
from apps.orders.services.item_grouping_service import (
    UNKNOWN_ITEM_NAME, ItemGroupingService,
)
from apps.orders.tests.base import OrdersTestCase, create_customer, make_order


class GroupingTests(OrdersTestCase):
    """Fixture menu: fries (cat 5, 1 min), burger (cat 3, 10 min), steak (cat 1, 20 min)."""

    def prep_list(self, **kwargs):
        return ItemGroupingService.get_prep_list(self.restaurant, **kwargs)

    def group(self, prep_list, name):
        return next(g for g in prep_list.groups if g.name == name)

    def test_same_item_from_different_orders_is_one_group(self):
        a = make_order(self.restaurant, [(self.burger, 2), (self.fries, 1)], batch_number=1, score=0.9)
        b = make_order(self.restaurant, [(self.burger, 1)], batch_number=1, score=0.5)
        burger = self.group(self.prep_list(), 'Burger')
        self.assertEqual(burger.total_quantity, 3)
        self.assertEqual(burger.order_count, 2)
        self.assertEqual([(l.order_id, l.quantity) for l in burger.lines], [(a.id, 2), (b.id, 1)])

    def test_group_carries_menu_item_details(self):
        make_order(self.restaurant, [(self.steak, 1)], batch_number=1)
        steak = self.group(self.prep_list(), 'Steak')
        self.assertEqual(steak.menu_item_id, self.steak.pk)
        self.assertEqual(steak.category, 'cat1')
        self.assertEqual(steak.prep_time, 20)

    def test_lines_follow_the_queue_not_the_creation_time(self):
        """Inside a batch the higher score is served first, so it must be listed first."""
        older_low = make_order(self.restaurant, [(self.burger, 1)], batch_number=1,
                               created_minutes_ago=30, score=0.2)
        newer_high = make_order(self.restaurant, [(self.burger, 1)], batch_number=1,
                                created_minutes_ago=1, score=0.9)
        lines = self.group(self.prep_list(), 'Burger').lines
        self.assertEqual([l.order_id for l in lines], [newer_high.id, older_low.id])
        self.assertEqual([l.queue_position for l in lines], [1, 2])

    def test_groups_are_sorted_by_first_order_that_needs_them(self):
        make_order(self.restaurant, [(self.steak, 1)], batch_number=1, score=0.9)
        make_order(self.restaurant, [(self.fries, 1), (self.steak, 1)], batch_number=1, score=0.5)
        names = [g.name for g in self.prep_list().groups]
        self.assertEqual(names, ['Steak', 'Fries'])

    def test_equal_first_position_is_broken_by_name(self):
        make_order(self.restaurant, [(self.steak, 1), (self.fries, 1), (self.burger, 1)], batch_number=1)
        names = [g.name for g in self.prep_list().groups]
        self.assertEqual(names, ['Burger', 'Fries', 'Steak'])

    def test_same_item_listed_twice_in_one_order_is_merged(self):
        order = make_order(self.restaurant, [(self.burger, 1)], batch_number=1)
        OrderItem.objects.create(order=order, menu_item=self.burger, quantity=2, unit_price=self.burger.price)
        burger = self.group(self.prep_list(), 'Burger')
        self.assertEqual(burger.order_count, 1)
        self.assertEqual(burger.total_quantity, 3)

    def test_deleted_menu_item_is_kept_so_the_cook_still_sees_it(self):
        order = make_order(self.restaurant, [(self.burger, 1)], batch_number=1)
        OrderItem.objects.create(order=order, menu_item=None, quantity=4)
        unknown = self.group(self.prep_list(), UNKNOWN_ITEM_NAME)
        self.assertIsNone(unknown.menu_item_id)
        self.assertEqual(unknown.total_quantity, 4)

    def test_empty_queue(self):
        result = self.prep_list()
        self.assertEqual((result.orders_considered, result.groups), (0, []))

    def test_order_without_items_is_counted_but_adds_nothing(self):
        make_order(self.restaurant, batch_number=1)
        result = self.prep_list()
        self.assertEqual(result.orders_considered, 1)
        self.assertEqual(result.groups, [])

    def test_only_pending_orders_are_grouped(self):
        make_order(self.restaurant, [(self.burger, 1)], batch_number=1, status='done')
        make_order(self.restaurant, [(self.burger, 1)], batch_number=1, status='cancelled')
        live = make_order(self.restaurant, [(self.burger, 1)], batch_number=1)
        lines = self.group(self.prep_list(), 'Burger').lines
        self.assertEqual([l.order_id for l in lines], [live.id])

    def test_other_restaurants_are_never_mixed_in(self):
        make_order(self.other_restaurant, [(self.other_menu['burger'], 5)], batch_number=1)
        self.assertEqual(self.prep_list().groups, [])


class WindowTests(OrdersTestCase):

    def setUp(self):
        self.first = make_order(self.restaurant, [(self.burger, 1)], batch_number=1, score=0.2)
        self.second = make_order(self.restaurant, [(self.burger, 1), (self.steak, 1)],
                                 batch_number=2, score=0.9)
        self.third = make_order(self.restaurant, [(self.burger, 1)], batch_number=3, score=0.5)

    def burger_group(self, **kwargs):
        result = ItemGroupingService.get_prep_list(self.restaurant, **kwargs)
        return next(g for g in result.groups if g.name == 'Burger'), result

    def test_default_looks_only_at_the_first_batch(self):
        burger, result = self.burger_group()
        self.assertEqual(result.orders_considered, 1)
        self.assertEqual([l.order_id for l in burger.lines], [self.first.id])

    def test_batch_limit_widens_the_window(self):
        burger, result = self.burger_group(batch_limit=2)
        self.assertEqual(result.orders_considered, 2)
        self.assertEqual([l.batch_number for l in burger.lines], [1, 2])

    def test_batch_limit_none_means_every_batch(self):
        _, result = self.burger_group(batch_limit=None)
        self.assertEqual(result.orders_considered, 3)

    def test_windowed_queue_never_lets_a_later_batch_jump_ahead(self):
        """Batch 2 has the best score but still comes after batch 1."""
        burger, _ = self.burger_group(batch_limit=None)
        self.assertEqual([l.order_id for l in burger.lines],
                         [self.first.id, self.second.id, self.third.id])

    def test_spans_batches_flag(self):
        self.assertFalse(self.burger_group()[0].spans_batches)
        self.assertTrue(self.burger_group(batch_limit=2)[0].spans_batches)

    def test_unwindowed_uses_pure_priority_and_ignores_batch_limit(self):
        burger, result = self.burger_group(windowed=False, batch_limit=1)
        self.assertEqual(result.orders_considered, 3)
        self.assertEqual([l.order_id for l in burger.lines],
                         [self.second.id, self.third.id, self.first.id])


class FilterTests(OrdersTestCase):

    def test_vip_only_and_normal_only(self):
        vip = make_order(self.restaurant, [(self.burger, 1)], special_flag=True, batch_number=1)
        normal = make_order(self.restaurant, [(self.burger, 1)], batch_number=1)
        ids = lambda **kw: [  # noqa: E731
            l.order_id for g in ItemGroupingService.get_prep_list(self.restaurant, **kw).groups for l in g.lines
        ]
        self.assertEqual(ids(vip_only=True), [vip.id])
        self.assertEqual(ids(vip_only=False), [normal.id])
        self.assertEqual(ids(vip_only=None), [vip.id, normal.id])

    def test_is_indoor_filter_and_channel(self):
        indoor = make_order(self.restaurant, [(self.burger, 1)], batch_number=1)
        delivery = make_order(self.restaurant, [(self.burger, 1)], is_indoor=False,
                              customer=create_customer(), batch_number=1)
        lines = lambda flag: ItemGroupingService.get_prep_list(  # noqa: E731
            self.restaurant, is_indoor=flag).groups[0].lines
        self.assertEqual([(l.order_id, l.channel) for l in lines(True)], [(indoor.id, 'dine_in')])
        self.assertEqual([(l.order_id, l.channel) for l in lines(False)], [(delivery.id, 'delivery')])


class SafetyTests(OrdersTestCase):

    def test_reading_the_prep_list_changes_nothing(self):
        """Fairness guard: it must never touch batches, scores or statuses."""
        for score, batch in ((0.9, 1), (0.4, 1), (0.7, 2)):
            make_order(self.restaurant, [(self.burger, 1)], batch_number=batch, score=score)
        snapshot = lambda: list(Order.objects.order_by('id').values_list(  # noqa: E731
            'id', 'batch_number', 'priority_score', 'status'))
        before = snapshot()
        ItemGroupingService.get_prep_list(self.restaurant, batch_limit=None)
        self.assertEqual(snapshot(), before)

    def test_order_number_and_channel_match_the_order_serializer(self):
        """The service formats these itself; this fails if the serializer's format changes."""
        order = make_order(self.restaurant, [(self.burger, 1)], batch_number=1)
        line = ItemGroupingService.get_prep_list(self.restaurant).groups[0].lines[0]
        shown = OrderListSerializer(Order.objects.get(pk=order.pk)).data
        self.assertEqual(line.order_number, shown['order_number'])
        self.assertEqual(line.channel, shown['channel'])

    def test_query_count_does_not_grow_with_order_count(self):
        def run():
            with CaptureQueriesContext(connection) as ctx:
                ItemGroupingService.get_prep_list(self.restaurant, batch_limit=None)
            return len(ctx)

        make_order(self.restaurant, [(self.fries, 1)], batch_number=1)
        small = run()
        for _ in range(12):
            make_order(self.restaurant, [(self.fries, 1), (self.steak, 2), (self.burger, 1)], batch_number=1)
        self.assertEqual(run(), small)
        self.assertLessEqual(small, 3)
