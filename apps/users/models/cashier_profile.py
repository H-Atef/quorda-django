import uuid

from django.conf import settings
from django.db import models


class CashierProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cashier_profile',
    )
    restaurant = models.ForeignKey(
        'users.RestaurantProfile',
        on_delete=models.CASCADE,
        related_name='cashiers',
    )
    is_active = models.BooleanField(default=True)
    can_set_vip = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Cashier Profile'
        verbose_name_plural = 'Cashier Profiles'

    def __str__(self):
        return f"Cashier {self.user.username} @ {self.restaurant.restaurant_name}"