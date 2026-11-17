from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.cart.models import Cart, CartItem
from apps.cart.exceptions import CartConflict
from apps.restaurants.models import MenuItem
from apps.orders.services import CustomerOrderService

MAX_UNITS_PER_ITEM = getattr(settings, 'CART_MAX_UNITS_PER_ITEM', 20)
MAX_DISTINCT_ITEMS = getattr(settings, 'CART_MAX_DISTINCT_ITEMS', 30)


class CartService:
    """Business logic for customer shopping carts."""

    @staticmethod
    def get_active_cart(customer):
        """Return the customer's active cart, creating an empty one if needed.

        Safe under concurrent creation thanks to the partial unique index
        ``unique_active_cart_per_customer``: duplicate creators hit an
        ``IntegrityError`` and retry, finding the cart another request made.
        """
        while True:
            cart = (
                Cart.objects.filter(customer=customer, status=Cart.Status.ACTIVE)
                .first()
            )
            if cart is not None:
                return cart
            try:
                return Cart.objects.create(customer=customer)
            except IntegrityError:
                continue

    @staticmethod
    def _lock_active_cart(customer, create_if_missing=False):
        """Lock and return the customer's active cart (must drive mutations).

        Acquires a write lock on the cart row (PostgreSQL row lock via UPDATE,
        SQLite database write lock) and re-checks the status so a concurrent
        checkout cannot mutate a cart that is already checked out.
        """
        while True:
            if create_if_missing:
                cart = CartService.get_active_cart(customer)
            else:
                cart = (
                    Cart.objects.filter(
                        customer=customer, status=Cart.Status.ACTIVE
                    ).first()
                )
                if cart is None:
                    return None
            try:
                with transaction.atomic():
                    Cart.objects.filter(pk=cart.pk).update(
                        updated_at=timezone.now()
                    )
                    cart = Cart.objects.get(pk=cart.pk)
                    if cart.status == Cart.Status.ACTIVE:
                        return cart
                    # A concurrent request checked the cart out. If we are not
                    # creating, this is a busy conflict; otherwise get a fresh
                    # active cart and retry (checked-out carts stay closed).
                    if not create_if_missing:
                        raise CartConflict(
                            code='cart_busy',
                            detail='Cart changed by a concurrent request. Please retry.',
                        )
            except CartConflict:
                if not create_if_missing:
                    raise
                # create_if_missing: loop to obtain a fresh active cart.
                continue

    @staticmethod
    def add_item(customer, menu_item_id, quantity=1, replace_cart=False):
        try:
            menu_item = (
                MenuItem.objects.select_related('restaurant')
                .get(pk=menu_item_id)
            )
        except MenuItem.DoesNotExist:
            raise ValidationError({'menu_item': 'Unknown menu item.'})
        if not menu_item.is_available:
            raise ValidationError({'menu_item': 'This menu item is unavailable.'})
        restaurant = menu_item.restaurant
        if restaurant is None or not restaurant.is_active:
            raise ValidationError(
                {'menu_item': 'The restaurant for this item is inactive.'}
            )

        for _ in range(5):
            cart = CartService.get_active_cart(customer)
            try:
                with transaction.atomic():
                    Cart.objects.filter(pk=cart.pk).update(
                        updated_at=timezone.now()
                    )
                    cart = Cart.objects.get(pk=cart.pk)
                    if cart.status != Cart.Status.ACTIVE:
                        continue  # checked out concurrently; fresh cart next
                    if replace_cart:
                        cart.items.all().delete()
                        cart.restaurant = restaurant
                        cart.save(update_fields=['restaurant', 'updated_at'])
                    else:
                        if cart.restaurant_id is None:
                            cart.restaurant = restaurant
                            cart.save(update_fields=['restaurant', 'updated_at'])
                        elif cart.restaurant_id != restaurant.id:
                            raise CartConflict(
                                code='restaurant_mismatch',
                                detail='Item is from a different restaurant.',
                                current_restaurant={
                                    'id': str(cart.restaurant.id),
                                    'restaurant_name': cart.restaurant.restaurant_name,
                                },
                                requested_restaurant={
                                    'id': str(restaurant.id),
                                    'restaurant_name': restaurant.restaurant_name,
                                },
                            )

                    item = cart.items.filter(menu_item=menu_item).first()
                    if item is not None:
                        new_quantity = item.quantity + quantity
                        if new_quantity > MAX_UNITS_PER_ITEM:
                            raise ValidationError(
                                {
                                    'quantity': (
                                        f'Exceeds max {MAX_UNITS_PER_ITEM} '
                                        'units per item.'
                                    )
                                }
                            )
                        item.quantity = new_quantity
                        item.added_price = menu_item.price
                        item.save(
                            update_fields=['quantity', 'added_price', 'updated_at']
                        )
                    else:
                        if cart.items.count() >= MAX_DISTINCT_ITEMS:
                            raise ValidationError(
                                {
                                    'cart': (
                                        f'Exceeds max {MAX_DISTINCT_ITEMS} '
                                        'distinct items.'
                                    )
                                }
                            )
                        CartItem.objects.create(
                            cart=cart,
                            menu_item=menu_item,
                            quantity=quantity,
                            added_price=menu_item.price,
                        )
                    return cart
            except CartConflict:
                raise
        raise CartConflict(
            code='cart_busy',
            detail='Cart changed by a concurrent request. Please retry.',
        )

    @staticmethod
    def set_quantity(customer, item_id, quantity):
        cart = (
            Cart.objects.filter(customer=customer, status=Cart.Status.ACTIVE)
            .first()
        )
        if cart is None:
            raise NotFound('Line not in your cart.')
        with transaction.atomic():
            Cart.objects.filter(pk=cart.pk).update(updated_at=timezone.now())
            cart = Cart.objects.get(pk=cart.pk)
            if cart.status != Cart.Status.ACTIVE:
                raise CartConflict(
                    code='cart_busy',
                    detail='Cart changed by a concurrent request. Please retry.',
                )
            item = get_object_or_404_cart_item(cart, item_id)
            item.quantity = quantity
            item.added_price = item.menu_item.price
            item.save(update_fields=['quantity', 'added_price', 'updated_at'])
        return cart

    @staticmethod
    def remove_item(customer, item_id):
        cart = (
            Cart.objects.filter(customer=customer, status=Cart.Status.ACTIVE)
            .first()
        )
        if cart is None:
            raise NotFound('Line not in your cart.')
        with transaction.atomic():
            Cart.objects.filter(pk=cart.pk).update(updated_at=timezone.now())
            cart = Cart.objects.get(pk=cart.pk)
            if cart.status != Cart.Status.ACTIVE:
                raise CartConflict(
                    code='cart_busy',
                    detail='Cart changed by a concurrent request. Please retry.',
                )
            item = get_object_or_404_cart_item(cart, item_id)
            item.delete()
            if cart.items.count() == 0:
                cart.restaurant = None
                cart.save(update_fields=['restaurant', 'updated_at'])
        return cart

    @staticmethod
    def clear_cart(customer):
        for _ in range(5):
            cart = CartService.get_active_cart(customer)
            try:
                with transaction.atomic():
                    Cart.objects.filter(pk=cart.pk).update(
                        updated_at=timezone.now()
                    )
                    cart = Cart.objects.get(pk=cart.pk)
                    if cart.status != Cart.Status.ACTIVE:
                        continue
                    cart.items.all().delete()
                    cart.restaurant = None
                    cart.save(update_fields=['restaurant', 'updated_at'])
                    return cart
            except CartConflict:
                raise
        raise CartConflict(
            code='cart_busy',
            detail='Cart changed by a concurrent request. Please retry.',
        )

    @staticmethod
    def checkout(customer, accept_price_changes=False):
        cart = CartService._lock_active_cart(customer, create_if_missing=False)
        if cart is None:
            # No active cart. If the customer already checked a cart out, this
            # is a double-checkout attempt on a closed cart.
            already_checked_out = (
                Cart.objects.filter(customer=customer)
                .exclude(status=Cart.Status.ACTIVE)
                .exists()
            )
            if already_checked_out:
                raise CartConflict(
                    code='cart_busy',
                    detail='Cart has already been checked out.',
                )
            raise ValidationError({'cart': 'No active cart to checkout.'})

        items = list(
            cart.items.select_related('menu_item').all()
        )
        if not items:
            raise ValidationError({'cart': 'Cannot checkout an empty cart.'})

        restaurant = cart.restaurant
        blocking_issues = []
        price_changes = []
        order_items_data = []

        if restaurant is None or not restaurant.is_active:
            blocking_issues.append(
                {
                    'code': 'restaurant_inactive',
                    'detail': 'The restaurant is inactive.',
                }
            )

        for item in items:
            menu_item = item.menu_item
            if menu_item is None or not menu_item.is_available:
                blocking_issues.append(
                    {
                        'code': 'item_unavailable',
                        'menu_item': str(item.menu_item_id),
                        'name': menu_item.name if menu_item else 'deleted item',
                    }
                )
                continue
            current_price = menu_item.price
            if item.added_price != current_price:
                price_changes.append(
                    {
                        'menu_item': str(menu_item.id),
                        'name': menu_item.name,
                        'old_price': str(item.added_price),
                        'new_price': str(current_price),
                    }
                )
            order_items_data.append(
                {'menu_item': menu_item, 'quantity': item.quantity}
            )

        if blocking_issues:
            raise CartConflict(
                code='cart_has_issues',
                detail=(
                    'Cart contains unavailable items or an inactive restaurant.'
                ),
                issues=blocking_issues,
            )

        if price_changes and not accept_price_changes:
            raise CartConflict(
                code='price_changed',
                detail='Prices changed since items were added.',
                issues=price_changes,
            )

        order = CustomerOrderService.create_order(
            customer, restaurant, {'order_items': order_items_data}
        )

        cart.status = Cart.Status.CHECKED_OUT
        cart.order = order
        cart.checked_out_at = timezone.now()
        cart.save(
            update_fields=['status', 'order', 'checked_out_at', 'updated_at']
        )
        return order, cart

    @staticmethod
    def expire_carts(days=30):
        cutoff = timezone.now() - timedelta(days=days)
        return (
            Cart.objects.filter(
                status=Cart.Status.ACTIVE, updated_at__lt=cutoff
            )
            .update(status=Cart.Status.ABANDONED)
        )


def get_object_or_404_cart_item(cart, item_id):
    try:
        return CartItem.objects.get(cart=cart, pk=item_id)
    except CartItem.DoesNotExist:
        raise NotFound('Line not in your cart.')
