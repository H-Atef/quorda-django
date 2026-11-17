from django.contrib import admin

from apps.cart.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ['menu_item', 'quantity', 'added_price']
    raw_id_fields = ['menu_item']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'restaurant', 'status', 'created_at']
    list_filter = ['status', 'restaurant']
    search_fields = ['id', 'customer__username', 'customer__email']
    readonly_fields = ['id', 'created_at', 'updated_at', 'checked_out_at']
    raw_id_fields = ['customer', 'restaurant', 'order']
    list_select_related = ['customer', 'restaurant']
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'cart', 'menu_item', 'quantity', 'added_price']
    search_fields = ['id', 'cart__id', 'menu_item__name']
    raw_id_fields = ['cart', 'menu_item']
    list_select_related = ['cart', 'menu_item']
