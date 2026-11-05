from django.core.exceptions import ObjectDoesNotExist

from apps.orders.models import Order


class PriorityCalculator:
    TIME_WEIGHT = 0.4
    QUANTITY_WEIGHT = 0.4
    CATEGORY_WEIGHT = 0.2

    @staticmethod
    def _get_params(restaurant_profile):
        try:
            params = restaurant_profile.calculation_params
        except (AttributeError, ObjectDoesNotExist):
            params = None
        if params:
            return {
                'time_weight': params.time_weight,
                'quantity_weight': params.quantity_weight,
                'category_weight': params.category_weight,
            }
        return {
            'time_weight': PriorityCalculator.TIME_WEIGHT,
            'quantity_weight': PriorityCalculator.QUANTITY_WEIGHT,
            'category_weight': PriorityCalculator.CATEGORY_WEIGHT,
        }

    @classmethod
    def compute_score(cls, order, items=None) -> float:
        if items is None:
            items = list(order.order_items.select_related('menu_item__category'))
        items = [i for i in items if i.menu_item is not None]
        if not items:
            return 0.0

        total_time = sum(i.menu_item.prep_time * i.quantity for i in items)
        total_qty = sum(i.quantity for i in items)

        time_score = min(2.0 / (total_time + 1), 1.0)
        quantity_score = min(2.0 / (total_qty + 1), 1.0)
        category_score = cls._category_score(items)

        p = cls._get_params(order.restaurant)
        return (p['time_weight'] * time_score
                + p['quantity_weight'] * quantity_score
                + p['category_weight'] * category_score)

    @staticmethod
    def _category_score(items) -> float:
        prios = [i.menu_item.category.priority
                 for i in items if i.menu_item.category is not None]
        return (max(prios) - 1) / 4 if prios else 0.0
