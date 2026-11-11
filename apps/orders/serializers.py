from rest_framework import serializers

from apps.orders.models import Order, OrderItem
from apps.users.models import RestaurantProfile, User


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'role']
        read_only_fields = fields


class OrderItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['menu_item', 'quantity']

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError('quantity must be at least 1.')
        return value


class OrderItemReadSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item', 'menu_item_name', 'quantity', 'unit_price']


class OrderSerializer(serializers.ModelSerializer):
    """Read serializer. Shared by restaurant-owner and customer views."""
    order_items = OrderItemReadSerializer(many=True, read_only=True)
    total_quantity = serializers.ReadOnlyField()
    total_prep_time = serializers.ReadOnlyField()
    total_cost = serializers.ReadOnlyField()
    channel = serializers.SerializerMethodField()
    created_by = UserSummarySerializer(read_only=True)
    shift_name = serializers.CharField(source='shift.name', read_only=True, allow_null=True)

    class Meta:
        model = Order
        fields = [
            'id', 'restaurant', 'customer', 'created_by', 'is_indoor', 'channel', 'status',
            'special_flag', 'priority_score', 'shift', 'shift_name', 'order_items',
            'total_quantity', 'total_prep_time', 'total_cost',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_channel(self, obj) -> str:
        return 'dine_in' if obj.is_indoor else 'delivery'


class OrderWriteSerializer(serializers.ModelSerializer):
    """Create/update serializer used by restaurant staff. Validates shape
    only — the view hands `validated_data` to OrderService, which owns the
    actual create/update logic."""
    order_items = OrderItemWriteSerializer(many=True)

    class Meta:
        model = Order
        fields = ['id', 'status', 'special_flag', 'order_items']
        read_only_fields = ['id']

    def validate_order_items(self, value):
        if self.partial and value is None:
            return value
        if not value:
            raise serializers.ValidationError('An order must contain at least one item.')
        return value


class CustomerOrderCreateSerializer(serializers.ModelSerializer):
    """Used by a customer placing a new delivery order. `restaurant` must
    be supplied by the customer; `customer` and `is_indoor` are set by
    CustomerOrderService, not exposed here."""
    order_items = OrderItemWriteSerializer(many=True)
    restaurant = serializers.PrimaryKeyRelatedField(queryset=RestaurantProfile.objects.filter(is_active=True))

    class Meta:
        model = Order
        fields = ['id', 'restaurant', 'order_items']
        read_only_fields = ['id']

    def validate_order_items(self, value):
        if not value:
            raise serializers.ValidationError('An order must contain at least one item.')
        return value


class CustomerOrderUpdateSerializer(serializers.ModelSerializer):
    """Used by a customer editing their own order. Only order_items can be
    changed, and only while status allows (enforced in CustomerOrderService)."""
    order_items = OrderItemWriteSerializer(many=True)

    class Meta:
        model = Order
        fields = ['order_items']

    def validate_order_items(self, value):
        if not value:
            raise serializers.ValidationError('An order must contain at least one item.')
        return value
