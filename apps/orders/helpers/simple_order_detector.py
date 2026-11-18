"""
SimpleOrderDetector — Django ORM-aware version.

An order is "simple" if:
  - total_quantity <= criteria.max_quantity
  - max category priority among its items >= criteria.min_category_priority
"""

from django.db.models import Sum, Max
from django.db.models.functions import Coalesce

class SimpleOrderDetector:
    
    @staticmethod
    def detect(orders, criteria):
        """
        Detects "simple" orders based on the given criteria.
        An order is "simple" if:
          - total_quantity <= criteria.max_quantity
          - max category priority among its items >= criteria.min_category_priority
        
        Args:
            orders: QuerySet of Order instances (e.g., Order.objects.all()).
            criteria: Object with `max_quantity` and `min_category_priority` attributes.
            
        Returns:
            QuerySet of matching Order instances.
        """
        
        return orders.annotate(
            # Coalesce ensures total_qty is 0 if the order has no items
            total_qty=Coalesce(Sum('order_items__quantity'), 0),
            # Coalesce ensures max_cat_prio is 0 if items have no category
            max_cat_prio=Coalesce(Max('order_items__menu_item__category__priority'), 0)
        ).filter(
            total_qty__lte=criteria.max_quantity,
            max_cat_prio__gte=criteria.min_category_priority
        )