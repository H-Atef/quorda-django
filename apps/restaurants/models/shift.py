import uuid
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import models


class ShiftDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(
        'users.RestaurantProfile',
        on_delete=models.CASCADE,
        related_name='shifts',
    )
    name = models.CharField(max_length=100)
    # Simple text like "08:00-16:00" or "08:00 to 16:00".
    time_range = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Shift Definition'
        verbose_name_plural = 'Shift Definitions'
        constraints = [
            models.UniqueConstraint(fields=['restaurant', 'name'], name='unique_shift_restaurant_name'),
        ]

    def _parse_range(self):
        """Split time_range into (start_minutes, end_minutes).

        Steps:
        1) Normalize separators: accept "08:00-16:00" or "08:00 to 16:00".
        2) Split into start text and end text.
        3) Parse each time as HH:MM.
        4) Convert to minutes from midnight (timestamp-like integer) so ranges
           can be compared with simple numbers.
        """
        text = (self.time_range or '').strip().lower().replace(' to ', '-')
        if '-' not in text:
            raise ValidationError({'time_range': 'Use format "HH:MM-HH:MM" (example: 08:00-16:00).'})

        start_text, end_text = [part.strip() for part in text.split('-', 1)]
        try:
            start_dt = datetime.strptime(start_text, '%H:%M')
            end_dt = datetime.strptime(end_text, '%H:%M')
        except ValueError:
            raise ValidationError({'time_range': 'Use valid times in format "HH:MM-HH:MM" (example: 08:00-16:00).'})

        start_minutes = start_dt.hour * 60 + start_dt.minute
        end_minutes = end_dt.hour * 60 + end_dt.minute
        if start_minutes == end_minutes:
            raise ValidationError({'time_range': 'Start and end time must be different.'})
        return start_minutes, end_minutes

    def clean(self):
        if not self.restaurant_id or not self.is_active or not self.time_range:
            return

        # Step A: parse the new shift into simple minute numbers.
        new_start, new_end = self._parse_range()

        # Step B: compare with other active shifts in the same restaurant.
        qs = ShiftDefinition.objects.filter(restaurant_id=self.restaurant_id, is_active=True)
        if self.pk:
            qs = qs.exclude(pk=self.pk)

        for other in qs:
            try:
                old_start, old_end = other._parse_range()
            except ValidationError:
                # Ignore existing rows that cannot be parsed; they should be fixed separately.
                continue

            # Step C: overlap check (simple same-day ranges).
            # Two ranges overlap when the new shift starts before the old shift ends
            # AND the old shift starts before the new shift ends.
            # Example overlap: 08:00-12:00 and 11:00-14:00.
            # Example no overlap: 08:00-12:00 and 12:00-16:00.
            if new_start < old_end and old_start < new_end:
                raise ValidationError({
                    'time_range': f'This shift overlaps with existing shift "{other.name}" ({other.time_range}).'
                })

    def __str__(self):
        return f"{self.name} ({self.time_range})"

