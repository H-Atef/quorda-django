# apps/restaurants/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
import uuid


class RestaurantCalculationParams(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.OneToOneField(
        'users.RestaurantProfile',
        on_delete=models.CASCADE,
        related_name='calculation_params'
    )
    time_weight = models.FloatField(
        default=0.4,
        validators=[MinValueValidator(0.0)],
        help_text='Weight for time inverse score (e.g. 0.4)',
    )
    quantity_weight = models.FloatField(
        default=0.4,
        validators=[MinValueValidator(0.0)],
        help_text='Weight for quantity inverse score (e.g. 0.4)',
    )
    category_weight = models.FloatField(
        default=0.2,
        validators=[MinValueValidator(0.0)],
        help_text='Weight for category priority score (e.g. 0.2)',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Restaurant Calculation Params'
        verbose_name_plural = 'Restaurant Calculation Params'
        ordering = ['-created_at']

    def clean(self):
        total = self.time_weight + self.quantity_weight + self.category_weight
        if abs(total - 1.0) > 0.0001:
            raise ValidationError("Weights must sum to 1.")

    def __str__(self):
        return f"Params for {self.restaurant.restaurant_name} (t={self.time_weight}, q={self.quantity_weight}, c={self.category_weight})"