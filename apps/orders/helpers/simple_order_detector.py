"""
SimpleOrderDetector — Django ORM-aware version.

An order is "simple" if:
  - total_quantity <= criteria.max_quantity
  - max category priority among its items >= criteria.min_category_priority
"""

from django.db.models import Sum, Max, OuterRef, Subquery
from django.db.models.functions import Coalesce


class SimpleOrderDetector:

    @staticmethod
    def detect(orders, criteria):
        total_qty_sq = (
            orders.model._default_manager
            .filter(pk=OuterRef('pk'))
            .annotate(t=Sum('order_items__quantity'))
            .values('t')[:1]
        )
        max_cat_sq = (
            orders.model._default_manager
            .filter(pk=OuterRef('pk'))
            .annotate(m=Max('order_items__menu_item__category__priority'))
            .values('m')[:1]
        )
        return orders.annotate(
            total_qty=Coalesce(Subquery(total_qty_sq), 0),
            max_cat_prio=Coalesce(Subquery(max_cat_sq), 0),
        ).filter(
            total_qty__lte=criteria.max_quantity,
            max_cat_prio__gte=criteria.min_category_priority,
        )