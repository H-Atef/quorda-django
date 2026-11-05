from rest_framework import serializers
from apps.restaurants.models import Category, MenuItem, Criteria, RestaurantCalculationParams
from apps.users.models import RestaurantProfile
from apps.restaurants.helpers.validators import ServiceErrorHandler as sh



class PublicRestaurantProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantProfile
        fields = ('id', 'restaurant_name', 'address', 'description', 'logo_url', 'is_active', 'created_at')


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'restaurant', 'name', 'priority', 'created_at')
        read_only_fields = ('id', 'restaurant', 'created_at')

    def validate_priority(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError('Priority must be between 1 and 5.')
        return value


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_priority = serializers.IntegerField(source='category.priority', read_only=True)

    class Meta:
        model = MenuItem
        fields = (
            'id', 'restaurant', 'category', 'category_name', 'category_priority',
            'name', 'prep_time', 'price', 'is_available',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'category_name', 'category_priority', 'created_at', 'updated_at','restaurant')

    def validate_category(self, category):
        if category is None:
            return None
        request = self.context.get('request')
        if request and hasattr(request.user, 'restaurant_profile'):
            if category.restaurant_id != request.user.restaurant_profile.id:
                raise serializers.ValidationError(
                    'This category does not belong to your restaurant.'
                )
        return category

    def validate(self, data):
        return data


class CriteriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Criteria
        fields = ('id', 'restaurant', 'max_quantity', 'min_category_priority', 'created_at', 'updated_at')
        read_only_fields = ('id','restaurant' ,'created_at', 'updated_at')

    def validate_min_category_priority(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError('min_category_priority must be between 1 and 5.')
        return value

    def validate(self, data):
        return data


class CalculationParamsSerializer(serializers.ModelSerializer):
    time_weight = serializers.FloatField(min_value=0.0)
    quantity_weight = serializers.FloatField(min_value=0.0)
    category_weight = serializers.FloatField(min_value=0.0)

    class Meta:
        model = RestaurantCalculationParams
        fields = ('id', 'restaurant', 'time_weight', 'quantity_weight', 'category_weight', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at', 'restaurant')

    def validate(self, data):
        if all(k in data for k in ('time_weight', 'quantity_weight', 'category_weight')):
            total = data['time_weight'] + data['quantity_weight'] + data['category_weight']
            if abs(total - 1.0) > 0.0001:
                raise serializers.ValidationError("Weights must sum to 1.")
        else:
            instance = getattr(self, 'instance', None)
            if instance is not None and any(k in data for k in ('time_weight', 'quantity_weight', 'category_weight')):
                total = (
                    data.get('time_weight', instance.time_weight)
                    + data.get('quantity_weight', instance.quantity_weight)
                    + data.get('category_weight', instance.category_weight)
                )
                if abs(total - 1.0) > 0.0001:
                    raise serializers.ValidationError("Weights must sum to 1.")
        return data
