from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
import uuid


class Category(models.Model):
    """
    A food category belonging to a restaurant.
    Priority ranges from 1 (lowest) to 5 (highest), matching the Python dataclass design.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(
        'users.RestaurantProfile',
        on_delete=models.CASCADE,
        related_name='categories',
    )
    name = models.CharField(max_length=100)
    priority = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='Priority 1 (normal) to 5 (serve sooner).',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['-priority', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['restaurant', 'name'],
                name='unique_category_restaurant_name'
            )
        ]

    def __str__(self):
        return f"{self.name} (priority={self.priority}) — {self.restaurant.restaurant_name}"
