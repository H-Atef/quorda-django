
from django.db import models


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    RESTAURANT = "restaurant", "Restaurant"
    CUSTOMER = "customer", "Customer"
    CASHIER = "cashier", "Cashier"