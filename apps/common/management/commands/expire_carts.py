from django.core.management.base import BaseCommand

from apps.cart.services import CartService


class Command(BaseCommand):
    help = 'Mark carts idle for N days as abandoned.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days of idleness before a cart is abandoned.',
        )

    def handle(self, *args, **options):
        days = options['days']
        count = CartService.expire_carts(days=days)
        self.stdout.write(
            self.style.SUCCESS(f'Marked {count} carts as abandoned (idle > {days} days).')
        )
