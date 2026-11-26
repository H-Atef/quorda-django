"""
Item grouping ("prep list") for the kitchen.

The kitchen display shows ORDERS in queue order. Cooks often prepare ITEMS in batches
instead: three tuna pizzas that belong to three different tickets go into the oven
together. This module turns the already-ordered queue into that item-centric view::

    queue (orders, in display order)        prep list (items)
    #1  2x Tuna Pizza, 1x Cola         ->   Tuna Pizza   x3   (#1 x2, #3 x1)
    #2  1x Margherita                       Cola          x2   (#1 x1, #3 x1)
    #3  1x Tuna Pizza, 1x Cola              Margherita    x1   (#2 x1)

Fairness rule: this service only RE-PRESENTS the queue. It never changes a batch number,
a priority score or the order of anything. Each line records the order's queue position and
batch, so the cook can see when an item is wanted by an order that is further back.

The default window is the first batch only (the orders that are being cooked now), so the
list does not invite cooking for orders that should wait their turn.
"""
from dataclasses import dataclass, field, replace
from typing import Optional
from uuid import UUID

from apps.orders.models import Order, OrderItem
from apps.orders.services.order_service import OrderService

DEFAULT_BATCH_LIMIT = 1
UNKNOWN_ITEM_NAME = 'Unavailable item'


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OrderLine:
    """How much of one menu item a single queued order needs."""
    order_id: UUID
    order_number: str
    queue_position: int            # 1-based position in the kitchen queue
    batch_number: Optional[int]
    special_flag: bool             # VIP order
    channel: str                   # 'dine_in' or 'delivery'
    quantity: int

    def with_added_quantity(self, extra: int) -> 'OrderLine':
        """Same line with `extra` more units (used when an order lists an item twice)."""
        return replace(self, quantity=self.quantity + extra)


@dataclass
class ItemGroup:
    """One menu item and every queued order that needs it, in queue order."""
    menu_item_id: Optional[UUID]   # None when the menu item was deleted after ordering
    name: str
    category: Optional[str]
    prep_time: Optional[int]       # minutes per unit
    lines: list = field(default_factory=list)

    def add_line(self, line: OrderLine) -> None:
        """Append a line; if the previous line is the same order, merge the quantities."""
        if self.lines and self.lines[-1].order_id == line.order_id:
            self.lines[-1] = self.lines[-1].with_added_quantity(line.quantity)
        else:
            self.lines.append(line)

    @property
    def total_quantity(self) -> int:
        return sum(line.quantity for line in self.lines)

    @property
    def order_count(self) -> int:
        return len(self.lines)

    @property
    def first_queue_position(self) -> int:
        return self.lines[0].queue_position

    @property
    def spans_batches(self) -> bool:
        """True when the item is wanted by orders from more than one batch."""
        return len({line.batch_number for line in self.lines}) > 1


@dataclass
class PrepList:
    """The full answer: how many orders were looked at and the item groups."""
    orders_considered: int
    groups: list


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class ItemGroupingService:

    @classmethod
    def get_prep_list(
        cls,
        restaurant,
        *,
        windowed=True,
        batch_limit=DEFAULT_BATCH_LIMIT,
        vip_only=None,
        is_indoor=None,
    ) -> PrepList:
        """
        Group identical menu items across the pending orders of `restaurant`.

        windowed:    True = use the batch-windowed queue order (Quorda's default);
                     False = pure priority order.
        batch_limit: only look at the first N batches (windowed mode only). Keeps the
                     list to the orders that are cookable now. None = every pending batch.
        vip_only:    None = all orders, True = VIP only, False = normal only.
        is_indoor:   None = both, True = dine-in, False = delivery.

        Groups are ordered by the queue position of the first order that needs the item,
        so the item the next order is waiting for is always at the top.
        """
        orders = cls._queued_orders(restaurant, windowed, batch_limit, vip_only, is_indoor)
        groups = cls._build_groups(orders)
        return PrepList(orders_considered=len(orders), groups=cls._sort_groups(groups))

    # -- step 1: the queue ---------------------------------------------------
    @staticmethod
    def _queued_orders(restaurant, windowed, batch_limit, vip_only, is_indoor) -> list:
        """Pending orders in display order. Reuses OrderService so there is one sort rule."""
        return list(OrderService.list_orders_qs(
            restaurant,
            vip_only=vip_only,
            is_indoor=is_indoor,
            windowed=windowed,
            batch_limit=batch_limit if windowed else None,
        ))

    # -- step 2: items -> groups --------------------------------------------
    @classmethod
    def _build_groups(cls, orders) -> dict:
        """Walk the queue once, front to back, adding every order item to its group."""
        groups = {}
        for position, order in enumerate(orders, start=1):
            for order_item in order.order_items.all():
                group = cls._group_for(groups, order_item.menu_item)
                group.add_line(cls._make_line(order, position, order_item))
        return groups

    @staticmethod
    def _group_for(groups, menu_item) -> ItemGroup:
        """Find or create the group for a menu item (deleted items share one group)."""
        key = menu_item.pk if menu_item is not None else None
        if key not in groups:
            groups[key] = ItemGroup(
                menu_item_id=key,
                name=menu_item.name if menu_item is not None else UNKNOWN_ITEM_NAME,
                category=ItemGroupingService._category_name(menu_item),
                prep_time=menu_item.prep_time if menu_item is not None else None,
            )
        return groups[key]

    @staticmethod
    def _category_name(menu_item) -> Optional[str]:
        category = menu_item.category if menu_item is not None else None
        return category.name if category is not None else None

    @staticmethod
    def _make_line(order: Order, position: int, order_item: OrderItem) -> OrderLine:
        return OrderLine(
            order_id=order.id,
            order_number=f'ORD-{str(order.id)[:4].upper()}',
            queue_position=position,
            batch_number=order.batch_number,
            special_flag=order.special_flag,
            channel='dine_in' if order.is_indoor else 'delivery',
            quantity=order_item.quantity,
        )

    # -- step 3: presentation order ------------------------------------------
    @staticmethod
    def _sort_groups(groups) -> list:
        """Earliest-needed item first; item name breaks ties so the output is stable."""
        return sorted(groups.values(), key=lambda g: (g.first_queue_position, g.name))
