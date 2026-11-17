import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.constraints import CheckConstraint, UniqueConstraint


class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(
        'cart.Cart',
        on_delete=models.CASCADE,
        related_name='items',
    )
    menu_item = models.ForeignKey(
        'restaurants.MenuItem',
        on_delete=models.CASCADE,
        related_name='cart_items',
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text='Quantity of this menu item in the cart.',
    )
    added_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text='Menu item price when the line was last added or changed.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'
        constraints = [
            UniqueConstraint(
                fields=['cart', 'menu_item'],
                name='unique_cartitem_cart_menuitem',
            ),
            CheckConstraint(
                condition=Q(quantity__gte=1),
                name='cartitem_quantity_gte_1',
            ),
        ]

    def __str__(self):
        return f'{self.quantity}x {self.menu_item.name} (Cart #{self.cart_id})'
