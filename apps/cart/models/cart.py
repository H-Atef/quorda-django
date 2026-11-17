import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint


class Cart(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        CHECKED_OUT = 'checked_out', 'Checked Out'
        ABANDONED = 'abandoned', 'Abandoned'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='carts',
    )
    restaurant = models.ForeignKey(
        'users.RestaurantProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='carts',
        help_text='Single restaurant for this cart. Set by the first item, cleared when empty.',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cart',
        help_text='Order created when this cart is checked out.',
    )
    checked_out_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cart'
        verbose_name_plural = 'Carts'
        constraints = [
            UniqueConstraint(
                fields=['customer'],
                condition=Q(status='active'),
                name='unique_active_cart_per_customer',
            ),
        ]
        indexes = [
            models.Index(
                fields=['status', 'updated_at'],
                name='cart_status_updated_idx',
            ),
        ]

    def __str__(self):
        return f'Cart #{self.id} — {self.customer.username} [{self.status}]'
