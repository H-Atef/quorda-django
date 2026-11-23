"""
SimpleOrderDetector — Django ORM-aware version.

An order is "simple" if:
  - total_quantity <= criteria.max_quantity
  - max category priority among its items >= criteria.min_category_priority
"""

from django.db.models import Max, Sum
from django.db.models.functions import Coalesce


class SimpleOrderDetector:

    @staticmethod
    def detect(orders, criteria):
        return orders.annotate(
            total_qty=Coalesce(Sum('order_items__quantity'), 0),
            max_cat_prio=Coalesce(
                Max('order_items__menu_item__category__priority'), 0,
            ),
        ).filter(
            total_qty__lte=criteria.max_quantity,
            max_cat_prio__gte=criteria.min_category_priority,
        )
