from django.apps import AppConfig


class CartConfig(AppConfig):
    name = 'apps.cart'
    verbose_name = 'Cart'

    def ready(self):
        import apps.cart.signals  # noqa: F401
