from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.cart.models import Cart, CartItem


@receiver(post_delete, sender=CartItem)
def _free_cart_restaurant_when_empty(sender, instance, **kwargs):
    """Clear the cart's restaurant when its last line is removed, including
    when lines disappear through cascade (e.g. a deleted menu item)."""
    cart = instance.cart
    if cart.items.count() == 0:
        Cart.objects.filter(pk=cart.pk).update(restaurant=None, updated_at=timezone.now())
