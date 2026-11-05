from apps.restaurants.models import Category, MenuItem, Criteria, RestaurantCalculationParams, ShiftDefinition
from apps.users.models.restaurant_profile import RestaurantProfile
from apps.restaurants.helpers.validators import ServiceErrorHandler
import uuid


class CategoryService:
    _UNIQUE_CONSTRAINTS = {
        'unique_category_restaurant_name': {'name': 'A category with this name already exists.'}
    }

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def list_for_restaurant(restaurant_profile):
        return Category.objects.filter(restaurant=restaurant_profile)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_does_not_exist(model_name="Category")
    def get_by_id(category_id, restaurant_profile):
        if isinstance(category_id, str):
            category_id = uuid.UUID(category_id)
        return Category.objects.get(pk=category_id, restaurant=restaurant_profile)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_integrity_error(_UNIQUE_CONSTRAINTS)
    def create(restaurant_profile, validated_data):
        return Category.objects.create(restaurant=restaurant_profile, **validated_data)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_integrity_error(_UNIQUE_CONSTRAINTS)
    def update(category, validated_data, partial=False):
        for attr, value in validated_data.items():
            setattr(category, attr, value)
        category.save()
        return category

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def delete(category):
        category.delete()


class MenuItemService:
    _UNIQUE_CONSTRAINTS = {
        'unique_menuitem_restaurant_name': {'name': 'A menu item with this name already exists.'}
    }

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def list_for_restaurant(restaurant_profile):
        return MenuItem.objects.filter(restaurant=restaurant_profile).select_related('category')

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_does_not_exist(model_name="MenuItem")
    def get_by_id(item_id, restaurant_profile):
        if isinstance(item_id, str):
            item_id = uuid.UUID(item_id)
        return MenuItem.objects.get(pk=item_id, restaurant=restaurant_profile)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_integrity_error(_UNIQUE_CONSTRAINTS)
    def create(restaurant_profile, validated_data):
        return MenuItem.objects.create(restaurant=restaurant_profile, **validated_data)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_integrity_error(_UNIQUE_CONSTRAINTS)
    def update(item, validated_data, partial=False):
        for attr, value in validated_data.items():
            setattr(item, attr, value)
        item.save()
        return item

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def delete(item):
        item.delete()


class CriteriaService:
    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def get_or_none(restaurant_profile):
        return getattr(restaurant_profile, 'criteria', None)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def create_or_update(restaurant_profile, validated_data):
        criteria, created = Criteria.objects.update_or_create(
            restaurant=restaurant_profile,
            defaults=validated_data,
        )
        return criteria, created
    
    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def delete(criteria):
        criteria.delete()


class CalculationParamsService:
    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_does_not_exist(model_name="CalculationParams")
    def get_for_restaurant(restaurant_profile):
        return RestaurantCalculationParams.objects.get(restaurant=restaurant_profile)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def create(restaurant_profile, validated_data):
        params = RestaurantCalculationParams(restaurant=restaurant_profile, **validated_data)
        params.full_clean()  
        params.save()
        return params

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def update(params_obj, validated_data, partial=False):
        for attr, value in validated_data.items():
            setattr(params_obj, attr, value)
        params_obj.full_clean()  
        params_obj.save()
        return params_obj

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def delete(params_obj):
        params_obj.delete()

class PublicRestaurantsService:
    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def list_active_restaurants():
        return RestaurantProfile.objects.filter(is_active=True)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_does_not_exist(message="Restaurant not found.")
    def get_active_restaurant(restaurant_id):
        return RestaurantProfile.objects.get(pk=restaurant_id, is_active=True)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def list_menu_items(restaurant_id):
        restaurant = PublicRestaurantsService.get_active_restaurant(restaurant_id)
        return MenuItemService.list_for_restaurant(restaurant)


class ShiftDefinitionService:
    _UNIQUE_CONSTRAINTS = {
        'unique_shift_restaurant_name': {'name': 'A shift with this name already exists.'}
    }

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def list_for_restaurant(restaurant_profile):
        return ShiftDefinition.objects.filter(restaurant=restaurant_profile)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_does_not_exist(model_name='Shift')
    def get_by_id(shift_id, restaurant_profile):
        return ShiftDefinition.objects.get(pk=shift_id, restaurant=restaurant_profile)

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_integrity_error(_UNIQUE_CONSTRAINTS)
    def create(restaurant_profile, validated_data):
        shift = ShiftDefinition(restaurant=restaurant_profile, **validated_data)
        shift.full_clean()
        shift.save()
        return shift

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    @ServiceErrorHandler.handle_integrity_error(_UNIQUE_CONSTRAINTS)
    def update(shift, validated_data, partial=False):
        for attr, value in validated_data.items():
            setattr(shift, attr, value)
        shift.full_clean()
        shift.save()
        return shift

    @staticmethod
    @ServiceErrorHandler.handle_all_exceptions()
    def deactivate(shift):
        shift.is_active = False
        shift.save(update_fields=['is_active'])