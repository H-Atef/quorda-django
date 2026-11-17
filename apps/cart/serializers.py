from decimal import Decimal

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.cart.models import Cart, CartItem


def _max_units_per_item():
    return getattr(settings, 'CART_MAX_UNITS_PER_ITEM', 20)


def _max_distinct_items():
    return getattr(settings, 'CART_MAX_DISTINCT_ITEMS', 30)


class CartItemSerializer(serializers.ModelSerializer):
    """Read-only cart line representation. Prices are live (current menu
    price) while ``added_price`` is the snapshot from when the line was last
    added or changed."""

    menu_item = serializers.UUIDField(source='menu_item.id', read_only=True)
    name = serializers.CharField(source='menu_item.name', read_only=True)
    category_name = serializers.CharField(
        source='menu_item.category.name', read_only=True, allow_null=True
    )
    unit_price = serializers.SerializerMethodField()
    added_price = serializers.DecimalField(max_digits=8, decimal_places=2)
    line_total = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    price_changed = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id',
            'menu_item',
            'name',
            'category_name',
            'quantity',
            'unit_price',
            'added_price',
            'line_total',
            'is_available',
            'price_changed',
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_unit_price(self, obj):
        if obj.menu_item is None:
            return None
        return str(obj.menu_item.price)

    @extend_schema_field(OpenApiTypes.STR)
    def get_line_total(self, obj):
        if obj.menu_item is None:
            return None
        return str(obj.menu_item.price * obj.quantity)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_available(self, obj):
        return obj.menu_item is not None and obj.menu_item.is_available

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_price_changed(self, obj):
        if obj.menu_item is None:
            return False
        return obj.added_price != obj.menu_item.price


class CartSerializer(serializers.ModelSerializer):
    restaurant = serializers.SerializerMethodField()
    items = CartItemSerializer(many=True, read_only=True)
    summary = serializers.SerializerMethodField()
    issues = serializers.SerializerMethodField()
    requires_price_confirmation = serializers.SerializerMethodField()
    can_checkout = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id',
            'status',
            'restaurant',
            'items',
            'summary',
            'issues',
            'requires_price_confirmation',
            'can_checkout',
            'updated_at',
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_restaurant(self, obj):
        if obj.restaurant is None:
            return None
        return {
            'id': obj.restaurant.id,
            'restaurant_name': obj.restaurant.restaurant_name,
        }

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_summary(self, obj):
        items = obj.items.all()
        distinct_items = items.count()
        item_count = sum(item.quantity for item in items)
        subtotal = sum(
            (item.menu_item.price * item.quantity)
            for item in items
            if item.menu_item is not None
        )
        return {
            'distinct_items': distinct_items,
            'item_count': item_count,
            'subtotal': str(subtotal),
        }

    @extend_schema_field(
        OpenApiTypes.OBJECT
    )  # array of issue objects, declared as object for simplicity
    def get_issues(self, obj):
        issues = []
        if obj.restaurant is None or not obj.restaurant.is_active:
            issues.append(
                {
                    'code': 'restaurant_inactive',
                    'detail': 'The restaurant is inactive.',
                }
            )
        for item in obj.items.all():
            menu_item = item.menu_item
            if menu_item is None or not menu_item.is_available:
                issues.append(
                    {
                        'code': 'item_unavailable',
                        'menu_item': str(item.menu_item_id),
                        'name': menu_item.name if menu_item else 'deleted item',
                    }
                )
        return issues

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_requires_price_confirmation(self, obj):
        return any(
            item.menu_item is not None and item.added_price != item.menu_item.price
            for item in obj.items.all()
        )

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_can_checkout(self, obj):
        return len(self.get_issues(obj)) == 0


class CartAddItemSerializer(serializers.Serializer):
    menu_item = serializers.UUIDField()
    quantity = serializers.IntegerField(default=1, min_value=1)
    replace_cart = serializers.BooleanField(default=False)

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError('Quantity must be at least 1.')
        if value > _max_units_per_item():
            raise serializers.ValidationError(
                f'Quantity exceeds max {_max_units_per_item()} units per item.'
            )
        return value


class CartItemQuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)

    def validate_quantity(self, value):
        if value > _max_units_per_item():
            raise serializers.ValidationError(
                f'Quantity exceeds max {_max_units_per_item()} units per item.'
            )
        return value


class CartCheckoutSerializer(serializers.Serializer):
    accept_price_changes = serializers.BooleanField(default=False)
