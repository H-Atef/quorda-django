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
        help_text='VIP order — sorted by ID before normal orders.',
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
        return sum(item.menu_item.prep_time * item.quantity for item in self.order_items.all())

    @property
    def total_cost(self) -> float:
        return sum(float(item.menu_item.price) * item.quantity for item in self.order_items.all())

    def recalculate_priority_score(self) -> None:
        """Recompute and persist priority_score. This is a regular method
        (not a property) so it can't collide with the model field and its
        call-site (`order.recalculate_priority_score()`) actually does
        what it looks like it does."""
        from apps.orders.helpers.priority_calculator import PriorityCalculator
        self.priority_score = PriorityCalculator.compute_score(self)
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

    class Meta:
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    @property
    def total_prep_time(self):
        return self.menu_item.prep_time * self.quantity

    @property
    def total_price(self):
        return float(self.menu_item.price) * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.menu_item.name} (Order #{self.order_id})"