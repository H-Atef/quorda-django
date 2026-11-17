from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.models import Cart
from apps.cart.serializers import (
    CartAddItemSerializer,
    CartCheckoutSerializer,
    CartItemQuantitySerializer,
    CartSerializer,
)
from apps.cart.services import CartService
from apps.orders.serializers import OrderSerializer
from apps.users.permissions import IsCustomer


@extend_schema(tags=['Cart'])
class CartAPIView(APIView):
    """Current cart (created empty on first use) and empty the cart."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        summary='Get the current cart',
        responses=CartSerializer,
    )
    def get(self, request):
        cart = (
            Cart.objects.select_related('restaurant')
            .prefetch_related('items__menu_item__category')
            .filter(customer=request.user, status=Cart.Status.ACTIVE)
            .first()
        )
        if cart is None:
            cart = CartService.get_active_cart(request.user)
        return Response(CartSerializer(cart).data)

    @extend_schema(
        summary='Empty the cart',
        responses=CartSerializer,
    )
    def delete(self, request):
        cart = CartService.clear_cart(request.user)
        cart = (
            Cart.objects.prefetch_related('items__menu_item__category')
            .get(pk=cart.pk)
        )
        return Response(CartSerializer(cart).data)


@extend_schema(tags=['Cart'])
class CartItemAddAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        summary='Add an item to the cart',
        request=CartAddItemSerializer,
        responses={201: CartSerializer},
    )
    def post(self, request):
        serializer = CartAddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = CartService.add_item(
            request.user,
            serializer.validated_data['menu_item'],
            serializer.validated_data.get('quantity', 1),
            serializer.validated_data.get('replace_cart', False),
        )
        cart = (
            Cart.objects.prefetch_related('items__menu_item__category')
            .get(pk=cart.pk)
        )
        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Cart'])
class CartItemDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        summary='Set a cart line quantity',
        request=CartItemQuantitySerializer,
        responses=CartSerializer,
    )
    def patch(self, request, item_id):
        serializer = CartItemQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = CartService.set_quantity(
            request.user, item_id, serializer.validated_data['quantity']
        )
        cart = (
            Cart.objects.prefetch_related('items__menu_item__category')
            .get(pk=cart.pk)
        )
        return Response(CartSerializer(cart).data)

    @extend_schema(
        summary='Remove a cart line',
        responses=CartSerializer,
    )
    def delete(self, request, item_id):
        cart = CartService.remove_item(request.user, item_id)
        cart = (
            Cart.objects.prefetch_related('items__menu_item__category')
            .get(pk=cart.pk)
        )
        return Response(CartSerializer(cart).data)


@extend_schema(tags=['Cart'])
class CartCheckoutAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        summary='Checkout: create an order and close the cart',
        request=CartCheckoutSerializer,
        responses={201: OrderSerializer},
    )
    def post(self, request):
        serializer = CartCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, _cart = CartService.checkout(
            request.user,
            serializer.validated_data.get('accept_price_changes', False),
        )
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
