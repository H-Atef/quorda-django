"""
OrderSorter — batch-based priority sorting for the kitchen display.

Core guarantees:
  - batch_number is assigned ONCE at order creation, scoped per restaurant.
  - New arrivals NEVER join older batches (no sliding).
  - Within a batch: VIPs first (oldest), then normals by -priority_score.
  - Holes left by delete/done persist until rebalance is called.
"""

from django.db import transaction
from django.db.models import Max

from apps.orders.models import Order


ACTIVE_STATUSES = (Order.Status.PENDING,)


class OrderSorter:

    # ================================================================
    # Batch assignment — called from OrderService.create_order
    # ================================================================

    @staticmethod
    @transaction.atomic
    def assign_batch_number(order, window_size=10):
        """
        Assign a batch_number to `order` (in memory; caller saves).

        Logic:
          1. Lock the restaurant row (serialize concurrent creates).
          2. Find max batch among this restaurant's ACTIVE orders only.
             (Done/cancelled orders don't hold a batch slot.)
          3. If no active orders → batch 1 (auto-restart after empty kitchen).
          4. If newest batch has < window_size pending → join it.
          5. Else → new batch (max + 1).

        Returns:
            The assigned batch_number.
        """
        from apps.users.models import RestaurantProfile

        RestaurantProfile.objects.select_for_update().get(pk=order.restaurant_id)

        max_batch = (
            Order.objects
            .filter(restaurant_id=order.restaurant_id, status__in=ACTIVE_STATUSES)
            .aggregate(m=Max('batch_number'))['m']
        )

        if not max_batch:
            order.batch_number = 1
            return order.batch_number

        pending_in_newest = (
            Order.objects
            .filter(
                restaurant_id=order.restaurant_id,
                batch_number=max_batch,
                status__in=ACTIVE_STATUSES,
            )
            .count()
        )

        if 0 < pending_in_newest < window_size:
            order.batch_number = max_batch
        else:
            order.batch_number = max_batch + 1
        return order.batch_number

    # ================================================================
    # Pure-Python helpers (used by the mock / tests / debugging)
    # In production, sorting is done via OrderService.list_orders (SQL).
    # ================================================================

    @staticmethod
    def _sort_key(order):
        """Tuple key: (VIP flag, [created_at | -score], created_at)."""
        if order.special_flag:
            return (0, order.created_at, 0.0)
        return (1, -order.priority_score, order.created_at)

    @classmethod
    def sort_with_batches(cls, orders):
        """In-memory sort (for tests). Production uses SQL order_by."""
        return sorted(
            orders,
            key=lambda o: (o.restaurant_id, o.batch_number, cls._sort_key(o)),
        )

    @staticmethod
    def get_vip_orders(orders):
        return sorted([o for o in orders if o.special_flag], key=lambda o: o.created_at)

    @staticmethod
    def get_normal_orders(orders):
        return sorted(
            [o for o in orders if not o.special_flag],
            key=lambda o: (-o.priority_score, o.created_at),
        )