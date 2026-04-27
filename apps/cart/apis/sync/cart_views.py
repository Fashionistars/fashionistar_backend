# apps/cart/apis/sync/cart_views.py
"""
DRF cart views.

All endpoints require IsAuthenticated + IsClient.
"""

import logging

from rest_framework import status, parsers
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.views import APIView

from apps.common.renderers import CustomJSONRenderer, success_response, error_response
from apps.common.permissions import IsClient, IsAuthenticatedAndActive
from apps.cart.serializers import CartSerializer, CartItemWriteSerializer
from apps.cart.services import (
    get_or_create_cart,
    add_item,
    remove_item,
    update_item_quantity,
    toggle_save_for_later,
    apply_coupon,
    remove_coupon,
    clear_cart,
    merge_guest_cart,
)

logger = logging.getLogger(__name__)

_RENDERERS = [CustomJSONRenderer, BrowsableAPIRenderer]
_PARSERS = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)


class CartView(APIView):
    """
    GET  /api/v1/cart/  — Retrieve user's cart with all items.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def get(self, request):
        cart = get_or_create_cart(request.user)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Cart retrieved.",
        )


class CartAddItemView(APIView):
    """
    POST /api/v1/cart/add/
    Body: { product_slug, quantity, variant_id? }
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request):
        serializer = CartItemWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        try:
            item = add_item(
                user=request.user,
                product_slug=serializer.validated_data["product_slug"],
                quantity=serializer.validated_data["quantity"],
                variant_id=serializer.validated_data.get("variant_id"),
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        cart = get_or_create_cart(request.user)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Item added to cart.",
            status=status.HTTP_200_OK,
        )


class CartRemoveItemView(APIView):
    """DELETE /api/v1/cart/items/<item_id>/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def delete(self, request, item_id):
        try:
            remove_item(user=request.user, item_id=item_id)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_404_NOT_FOUND)
        cart = get_or_create_cart(request.user)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Item removed from cart.",
        )


class CartUpdateQuantityView(APIView):
    """PATCH /api/v1/cart/items/<item_id>/quantity/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def patch(self, request, item_id):
        quantity = request.data.get("quantity")
        if quantity is None:
            return error_response(message="quantity is required.", status=status.HTTP_400_BAD_REQUEST)
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return error_response(message="quantity must be an integer.", status=status.HTTP_400_BAD_REQUEST)
        try:
            update_item_quantity(user=request.user, item_id=item_id, quantity=quantity)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        cart = get_or_create_cart(request.user)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Quantity updated.",
        )


class CartSaveForLaterView(APIView):
    """POST /api/v1/cart/items/<item_id>/save-later/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request, item_id):
        try:
            toggle_save_for_later(user=request.user, item_id=item_id)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_404_NOT_FOUND)
        cart = get_or_create_cart(request.user)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Item toggled.",
        )


class CartCouponView(APIView):
    """
    POST   /api/v1/cart/coupon/  — Apply coupon.
    DELETE /api/v1/cart/coupon/  — Remove coupon.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request):
        code = request.data.get("code", "").strip()
        if not code:
            return error_response(message="Coupon code is required.", status=status.HTTP_400_BAD_REQUEST)
        try:
            cart = apply_coupon(user=request.user, code=code)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message=f"Coupon '{code}' applied.",
        )

    def delete(self, request):
        cart = remove_coupon(user=request.user)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Coupon removed.",
        )


class CartClearView(APIView):
    """DELETE /api/v1/cart/clear/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def delete(self, request):
        clear_cart(user=request.user)
        cart = get_or_create_cart(request.user)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Cart cleared.",
        )


class CartMergeView(APIView):
    """
    POST /api/v1/cart/merge/
    Body: { items: [{ product_slug, quantity, variant_id? }] }
    Called by frontend immediately after successful login to merge guest cart.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request):
        guest_items = request.data.get("items", [])
        if not isinstance(guest_items, list):
            return error_response(message="items must be a list.", status=status.HTTP_400_BAD_REQUEST)
        cart = merge_guest_cart(user=request.user, guest_items=guest_items)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message=f"Guest cart merged: {len(guest_items)} item(s) processed.",
        )
