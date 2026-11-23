from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.orders.models import Order
from apps.users.models import RestaurantProfile


ACTIVE_STATUSES = (Order.Status.PENDING,)


class BatchService:
    """Batch management operations for orders."""

    @classmethod
    @transaction.atomic
    def rebalance_batches(cls, restaurant, window_size=10, target_batch=None):
        """
        Fill holes in batches by promoting the oldest pending orders
        from later batches into earlier ones, cascading left-to-right.

        Args:
            restaurant:   RestaurantProfile instance.
            window_size:  Batch size target.
            target_batch: If set, only rebalance that specific batch.
                          Otherwise rebalance from the lowest batch upward.

        Returns:
            {
                'rebalanced': <count>,
                'summary_before': [...],
                'summary_after': [...],
            }

        Guarantees:
          - Only pending orders are considered (done/cancelled
            orders keep their original batch_number for audit).
          - Promotions are always oldest-first (by created_at).
          - Cascade stops when no more pending orders exist in later batches.
        """
        # Serialize concurrent rebalances on this restaurant
        RestaurantProfile.objects.select_for_update().get(pk=restaurant.pk)

        summary_before = cls._batch_summary(restaurant, ACTIVE_STATUSES)
        rebalanced = 0

        # Which batches do we touch?
        if target_batch is not None:
            batches = [target_batch]
        else:
            batches = (
                Order.objects
                .filter(restaurant=restaurant, status__in=ACTIVE_STATUSES)
                .values_list('batch_number', flat=True)
                .distinct()
                .order_by('batch_number')
            )
            batches = list(batches)

        for batch_num in batches:
            pending_here = Order.objects.filter(
                restaurant=restaurant,
                batch_number=batch_num,
                status__in=ACTIVE_STATUSES,
            ).count()

            holes = window_size - pending_here
            if holes <= 0:
                continue

            # Pull oldest from any later batch
            promote = list(
                Order.objects
                .filter(
                    restaurant=restaurant,
                    batch_number__gt=batch_num,
                    status__in=ACTIVE_STATUSES,
                )
                .order_by('batch_number', 'created_at')[:holes]
            )

            if not promote:
                continue  # no more pending orders to promote

            old_batch_by_order = {o.id: o.batch_number for o in promote}

            Order.objects.filter(pk__in=old_batch_by_order.keys()).update(
                batch_number=batch_num,
            )
            rebalanced += len(promote)

        summary_after = cls._batch_summary(restaurant, ACTIVE_STATUSES)
        return {
            'rebalanced': rebalanced,
            'summary_before': summary_before,
            'summary_after': summary_after,
        }

    @classmethod
    @transaction.atomic
    def reset_batches(cls, restaurant, mode='completed', actor=None):
        """
        Reset batch_number for a restaurant.

        Args:
            restaurant:  RestaurantProfile instance.
            mode:
              'completed' (SAFE, default)
                  Reset only DONE/CANCELLED orders to batch_number=0.
                  Pending orders keep their batches. Next new order continues
                  from current max pending batch.

              'all' (DANGEROUS)
                  Reset EVERY order to batch_number=0. Only allowed when
                  there are NO pending orders. Forces a clean slate.
                  Use at start of a new day/shift.

        Returns:
            {
                'mode': 'completed' | 'all',
                'restaurant_id': <id>,
                'restaurant_name': <name>,
                'orders_reset': <count>,
            }

        Raises:
            ValidationError: if mode='all' but pending orders exist.
        """
        # Lock to prevent concurrent resets / new order creation
        RestaurantProfile.objects.select_for_update().get(pk=restaurant.pk)

        if mode == 'all':
            active_count = Order.objects.filter(
                restaurant=restaurant,
                status__in=[Order.Status.PENDING],
            ).count()
            if active_count > 0:
                raise ValidationError({
                    'mode': (
                        f'Cannot reset all batches: {active_count} pending '
                        f'orders exist. Complete or cancel them first, or use mode=completed.'
                    )
                })
            qs = Order.objects.filter(restaurant=restaurant)
        elif mode == 'completed':
            qs = Order.objects.filter(
                restaurant=restaurant,
                status__in=[Order.Status.DONE, Order.Status.CANCELLED],
            )
        else:
            raise ValidationError({'mode': "Must be 'completed' or 'all'."})

        reset_count = qs.update(batch_number=0)

        return {
            'mode': mode,
            'restaurant_id': str(restaurant.id),
            'restaurant_name': restaurant.restaurant_name,
            'orders_reset': reset_count,
        }

    @staticmethod
    def _batch_summary(restaurant, active_statuses):
        """Return [{batch_number, pending, holes}, ...] for monitoring."""
        from django.db.models import Count

        rows = (
            Order.objects
            .filter(restaurant=restaurant, status__in=active_statuses)
            .values('batch_number')
            .annotate(pending=Count('id'))
            .order_by('batch_number')
        )
        return list(rows)