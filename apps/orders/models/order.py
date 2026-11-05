from django.db import models
from django.conf import settings
import uuid


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PREPARING = 'preparing', 'Preparing'
        DONE = 'done', 'Done'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(
        'users.RestaurantProfile',
        on_delete=models.CASCADE,
        related_name='orders',
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        help_text='Required when is_indoor=False (delivery). Optional for dine-in.',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='created_orders',
    )
    is_indoor = models.BooleanField(
        default=True,
        help_text='True = dine-in (no customer required). False = delivery (customer required).',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    special_flag = models.BooleanField(
        default=False,
        help_text='VIP order — ranked before normal orders (oldest first among VIPs).',
    )
    shift = models.ForeignKey(
        'restaurants.ShiftDefinition',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='orders',
    )

    priority_score = models.FloatField(default=0.0, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self.order_items.all())

    @property
    def total_prep_time(self) -> int:
        return sum(
            (item.menu_item.prep_time * item.quantity) if item.menu_item else 0
            for item in self.order_items.all()
        )

    @property
    def total_cost(self) -> float:
        total = 0.0
        for item in self.order_items.all():
            if item.unit_price is not None:
                total += float(item.unit_price) * item.quantity
            elif item.menu_item:
                total += float(item.menu_item.price) * item.quantity
        return total

    def recalculate_priority_score(self, items=None) -> None:
        """Recompute and persist priority_score."""
        from apps.orders.helpers.priority_calculator import PriorityCalculator
        self.priority_score = PriorityCalculator.compute_score(self, items=items)
        self.save(update_fields=['priority_score', 'updated_at'])

    def __str__(self):
        return f"Order #{self.id} — {self.restaurant.restaurant_name} [{self.status}]"


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='order_items',
    )
    menu_item = models.ForeignKey(
        'restaurants.MenuItem',
        on_delete=models.SET_NULL,
        related_name='order_items',
        null=True,
        blank=True
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=8, decimal_places=2, null=True)

    class Meta:
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    @property
    def total_prep_time(self):
        return (self.menu_item.prep_time * self.quantity) if self.menu_item else 0

    @property
    def total_price(self):
        if self.unit_price is not None:
            return float(self.unit_price) * self.quantity
        return (float(self.menu_item.price) * self.quantity) if self.menu_item else 0.0

    def __str__(self):
        name = self.menu_item.name if self.menu_item else 'deleted item'
        return f"{self.quantity}x {name} (Order #{self.order_id})"