from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.users.models import RestaurantProfile, CashierProfile
from apps.restaurants.models import Category, MenuItem, ShiftDefinition
from apps.cart.models import Cart, CartItem
from apps.orders.models import Order, OrderItem
from apps.orders.services.order_service import OrderService
from apps.orders.services.customer_order_service import CustomerOrderService

ADMIN_USERNAME = 'admin'
ADMIN_EMAIL = 'admin@quorda.local'
ADMIN_PASSWORD = 'admin123'
SEED_PASSWORD = 'seed123'
ORDERS_PER_RESTAURANT = 40


class Command(BaseCommand):
    help = 'Truncates all data except the admin user, then seeds restaurants, users, categories, menu items, shifts, orders, and carts.'

    def handle(self, *args, **options):
        User = get_user_model()

        with transaction.atomic():
            self._truncate(User)
            admin = self._ensure_admin(User)
            self._seed(User, admin)

        self.stdout.write(
            self.style.SUCCESS('Database reset complete: all data truncated except admin, then seeded.')
        )

    def _truncate(self, User):
        CartItem.objects.all().delete()
        OrderItem.objects.all().delete()
        Cart.objects.all().delete()
        Order.objects.all().delete()
        MenuItem.objects.all().delete()
        Category.objects.all().delete()
        ShiftDefinition.objects.all().delete()
        CashierProfile.objects.all().delete()
        RestaurantProfile.objects.all().delete()
        User.objects.exclude(username=ADMIN_USERNAME).delete()
        self.stdout.write(self.style.WARNING('All data truncated (admin user kept).'))

    def _ensure_admin(self, User):
        admin, created = User.objects.get_or_create(
            username=ADMIN_USERNAME,
            defaults={
                'email': ADMIN_EMAIL,
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        if created:
            admin.set_password(ADMIN_PASSWORD)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f'Created admin user: {ADMIN_USERNAME}'))
        return admin

    def _seed(self, User, admin):
        restaurants = self._create_restaurants(User)
        self._create_categories_and_menu_items(restaurants)
        self._create_shifts(restaurants)
        self._create_cashiers(User, restaurants)
        customers = self._create_customers(User)
        self._create_carts(customers, restaurants)
        self._create_orders(customers, restaurants)

    def _create_restaurants(self, User):
        created = []
        data = [
            {
                'username': 'owner_pizza',
                'email': 'owner@pizzapalace.local',
                'restaurant_name': 'Pizza Palace',
                'address': '123 Main St, Cairo',
                'description': 'Best pizza in town.',
            },
            {
                'username': 'owner_sushi',
                'email': 'owner@sushihouse.local',
                'restaurant_name': 'Sushi House',
                'address': '456 Nile Corniche, Cairo',
                'description': 'Fresh sushi and sashimi.',
            },
        ]
        for entry in data:
            user = User.objects.create_user(
                username=entry['username'],
                email=entry['email'],
                password=SEED_PASSWORD,
                role='restaurant',
            )
            profile = RestaurantProfile.objects.create(
                user=user,
                restaurant_name=entry['restaurant_name'],
                address=entry['address'],
                description=entry['description'],
                is_active=True,
            )
            created.append(profile)
            self.stdout.write(self.style.SUCCESS(f'Created restaurant: {profile.restaurant_name}'))
        return created

    def _create_categories_and_menu_items(self, restaurants):
        menus = {
            'Pizza Palace': {
                'Pizzas': [
                    ('Margherita Pizza', 12, 150.00),
                    ('Pepperoni Pizza', 15, 180.00),
                    ('BBQ Chicken Pizza', 20, 200.00),
                    ('Hawaiian Pizza', 15, 170.00),
                    ('Veggie Supreme Pizza', 18, 160.00),
                    ('Meat Lovers Pizza', 20, 210.00),
                ],
                'Pasta': [
                    ('Spaghetti Carbonara', 15, 130.00),
                    ('Penne Arrabbiata', 12, 120.00),
                    ('Fettuccine Alfredo', 15, 140.00),
                ],
                'Salads': [
                    ('Caesar Salad', 8, 90.00),
                    ('Greek Salad', 7, 80.00),
                ],
                'Desserts': [
                    ('Tiramisu', 5, 70.00),
                    ('Cheesecake', 5, 75.00),
                ],
                'Drinks': [
                    ('Coca Cola', 2, 25.00),
                    ('Sprite', 2, 25.00),
                    ('Water', 1, 15.00),
                ],
            },
            'Sushi House': {
                'Nigiri': [
                    ('Salmon Nigiri', 5, 90.00),
                    ('Tuna Nigiri', 5, 95.00),
                    ('Shrimp Nigiri', 5, 85.00),
                ],
                'Rolls': [
                    ('Tuna Roll', 10, 110.00),
                    ('Salmon Roll', 10, 115.00),
                    ('California Roll', 8, 100.00),
                    ('Spicy Tuna Roll', 12, 125.00),
                ],
                'Sashimi': [
                    ('Sashimi Platter', 15, 220.00),
                    ('Salmon Sashimi', 10, 180.00),
                ],
                'Appetizers': [
                    ('Edamame', 5, 45.00),
                    ('Miso Soup', 5, 40.00),
                    ('Gyoza', 10, 70.00),
                ],
                'Drinks': [
                    ('Green Tea', 3, 30.00),
                    ('Sake', 3, 60.00),
                    ('Water', 1, 15.00),
                ],
            },
        }
        for restaurant in restaurants:
            cat_items = menus.get(restaurant.restaurant_name, {})
            priority = 1
            for cat_name, items in cat_items.items():
                category, _ = Category.objects.get_or_create(
                    restaurant=restaurant,
                    name=cat_name,
                    defaults={'priority': priority},
                )
                priority += 1
                for name, prep_time, price in items:
                    MenuItem.objects.create(
                        restaurant=restaurant,
                        category=category,
                        name=name,
                        prep_time=prep_time,
                        price=price,
                        is_available=True,
                    )
            self.stdout.write(
                self.style.SUCCESS(f'Created categories and menu items for: {restaurant.restaurant_name}')
            )

    def _create_shifts(self, restaurants):
        shifts_data = [
            ('Morning', '08:00-16:00'),
            ('Afternoon', '16:00-00:00'),
        ]
        for restaurant in restaurants:
            for name, time_range in shifts_data:
                ShiftDefinition.objects.create(
                    restaurant=restaurant,
                    name=name,
                    time_range=time_range,
                    is_active=True,
                )
            self.stdout.write(
                self.style.SUCCESS(f'Created shifts for: {restaurant.restaurant_name}')
            )

    def _create_cashiers(self, User, restaurants):
        cashier_data = [
            ('cashier_john', 'john@cashier.local', 'John'),
            ('cashier_jane', 'jane@cashier.local', 'Jane'),
        ]
        for idx, restaurant in enumerate(restaurants):
            for username, email, first_name in cashier_data:
                user = User.objects.create_user(
                    username=f"{username}_{restaurant.restaurant_name.split()[0].lower()}",
                    email=f"{username}_{restaurant.restaurant_name.split()[0].lower()}@cashier.local",
                    password=SEED_PASSWORD,
                    role='cashier',
                    first_name=first_name,
                )
                CashierProfile.objects.create(
                    user=user,
                    restaurant=restaurant,
                    is_active=True,
                    can_set_vip=(idx % 2 == 0),
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Created cashier: {username} @ {restaurant.restaurant_name}')
                )

    def _create_customers(self, User):
        created = []
        data = [
            ('customer_alice', 'alice@customer.local', 'Alice'),
            ('customer_bob', 'bob@customer.local', 'Bob'),
            ('customer_carol', 'carol@customer.local', 'Carol'),
            ('customer_dave', 'dave@customer.local', 'Dave'),
            ('customer_eve', 'eve@customer.local', 'Eve'),
        ]
        for username, email, first_name in data:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=SEED_PASSWORD,
                role='customer',
                first_name=first_name,
            )
            created.append(user)
            self.stdout.write(self.style.SUCCESS(f'Created customer: {username}'))
        return created

    def _create_carts(self, customers, restaurants):
        pizza = restaurants[0]
        sushi = restaurants[1]
        pizza_items = list(MenuItem.objects.filter(restaurant=pizza))
        sushi_items = list(MenuItem.objects.filter(restaurant=sushi))

        cart_data = [
            (customers[0], pizza, pizza_items),
            (customers[1], sushi, sushi_items),
        ]
        for customer, restaurant, items in cart_data:
            cart = Cart.objects.create(customer=customer, restaurant=restaurant, status='active')
            chosen = items[:5] if len(items) >= 5 else items
            for menu_item in chosen:
                CartItem.objects.create(
                    cart=cart,
                    menu_item=menu_item,
                    quantity=1,
                    added_price=menu_item.price,
                )
            self.stdout.write(
                self.style.SUCCESS(f'Created active cart with {len(chosen)} items for {customer.username} at {restaurant.restaurant_name}')
            )

    def _create_orders(self, customers, restaurants):
        for restaurant in restaurants:
            items = list(MenuItem.objects.filter(restaurant=restaurant))
            if not items:
                continue
            for i in range(ORDERS_PER_RESTAURANT):
                customer = customers[i % len(customers)]
                is_indoor = (i % 2 == 0)
                line_count = (i % 4) + 1
                chosen = items[:line_count] if len(items) >= line_count else items
                order_items = [
                    {'menu_item': menu_item, 'quantity': (i % 3) + 1}
                    for menu_item in chosen
                ]

                if is_indoor:
                    cashier = restaurant.cashiers.filter(is_active=True).first()
                    actor = cashier.user if cashier else customer
                    order = OrderService.create_order(
                        restaurant=restaurant,
                        validated_data={
                            'order_items': order_items,
                            'special_flag': False,
                            'status': 'pending',
                        },
                        actor=actor,
                        window_size=10,
                    )
                    order.is_indoor = True
                    order.customer = customer
                    order.created_by = customer
                    order.status = 'pending'
                    order.save(update_fields=['is_indoor', 'customer', 'created_by', 'status'])
                else:
                    order = CustomerOrderService.create_order(
                        customer=customer,
                        restaurant=restaurant,
                        validated_data={
                            'order_items': order_items,
                            'status': 'pending',
                        },
                    )
                    order.status = 'pending'
                    order.save(update_fields=['status'])

            self.stdout.write(
                self.style.SUCCESS(f'Created {ORDERS_PER_RESTAURANT} orders for: {restaurant.restaurant_name}')
            )
