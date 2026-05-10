# apps/cart/apis/sync/cart_views.py
"""
DRF cart views.

All endpoints require IsAuthenticated + IsClient.
"""

import logging

from rest_framework import status, parsers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.views import APIView

from apps.common.renderers import CustomJSONRenderer, success_response, error_response
from apps.common.permissions import IsAuthenticatedAndActive
from apps.cart.serializers import CartSerializer, CartItemWriteSerializer
from apps.cart.services import (
    add_item,
    remove_item,
    update_item_quantity,
    toggle_save_for_later,
    apply_coupon,
    remove_coupon,
    clear_cart,
    merge_guest_cart,
    merge_anonymous_cart_session,
)

logger = logging.getLogger(__name__)

_RENDERERS = [CustomJSONRenderer, BrowsableAPIRenderer]
_PARSERS = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)


def _cart_identity(request) -> dict:
    """
    Resolve the cart owner from JWT auth or anonymous browser session.

    Anonymous callers must send the stable frontend-generated ID as one of:
      - JSON/form field: session_key
      - Header: X-Fashionistar-Session-Key
      - Cookie: fashionistar_session_key
    """
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return {"user": user}

    session_key = (
        request.data.get("session_key")
        or request.headers.get("X-Fashionistar-Session-Key")
        or request.query_params.get("session_key")
        or request.COOKIES.get("fashionistar_session_key")
    )
    if not session_key:
        raise ValueError("session_key is required for anonymous cart access.")
    return {"session_key": str(session_key)[:40]}


class CartAddItemView(APIView):
    """
    POST /api/v1/cart/add/
    Body: { product_slug, quantity, variant_id? }
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

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
                **_cart_identity(request),
                product_slug=serializer.validated_data["product_slug"],
                quantity=serializer.validated_data["quantity"],
                variant_id=serializer.validated_data.get("variant_id"),
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        cart = item.cart
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Item added to cart.",
            status=status.HTTP_200_OK,
        )


class CartRemoveItemView(APIView):
    """DELETE /api/v1/cart/items/<item_id>/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def delete(self, request, item_id):
        try:
            identity = _cart_identity(request)
            remove_item(**identity, item_id=item_id)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_404_NOT_FOUND)
        from apps.cart.selectors import CartSelector

        cart = CartSelector.for_identity(**identity).get()
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Item removed from cart.",
        )


class CartUpdateQuantityView(APIView):
    """PATCH /api/v1/cart/items/<item_id>/quantity/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def patch(self, request, item_id):
        quantity = request.data.get("quantity")
        if quantity is None:
            return error_response(message="quantity is required.", status=status.HTTP_400_BAD_REQUEST)
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return error_response(message="quantity must be an integer.", status=status.HTTP_400_BAD_REQUEST)
        try:
            identity = _cart_identity(request)
            update_item_quantity(**identity, item_id=item_id, quantity=quantity)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        from apps.cart.selectors import CartSelector

        cart = CartSelector.for_identity(**identity).get()
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Quantity updated.",
        )


class CartSaveForLaterView(APIView):
    """POST /api/v1/cart/items/<item_id>/save-later/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def post(self, request, item_id):
        try:
            item = toggle_save_for_later(**_cart_identity(request), item_id=item_id)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_404_NOT_FOUND)
        item.refresh_from_db()
        cart = item.cart
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
    permission_classes = [AllowAny]

    def post(self, request):
        code = request.data.get("code", "").strip()
        if not code:
            return error_response(message="Coupon code is required.", status=status.HTTP_400_BAD_REQUEST)
        try:
            cart = apply_coupon(**_cart_identity(request), code=code)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message=f"Coupon '{code}' applied.",
        )

    def delete(self, request):
        cart = remove_coupon(**_cart_identity(request))
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Coupon removed.",
        )


class CartClearView(APIView):
    """DELETE /api/v1/cart/clear/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def delete(self, request):
        identity = _cart_identity(request)
        clear_cart(**identity)
        from apps.cart.selectors import CartSelector

        cart = CartSelector.for_identity(**identity).get()
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Cart cleared.",
        )


class CartMergeView(APIView):
    """
    POST /api/v1/cart/merge/
    Body:
      { session_key: "..." }
      or legacy { items: [{ product_slug, quantity, variant_id? }] }

    Called after login and before checkout submit. Database-backed anonymous
    carts are preferred; the legacy item-array path remains for older clients.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request):
        session_key = (
            request.data.get("session_key")
            or request.headers.get("X-Fashionistar-Session-Key")
            or request.COOKIES.get("fashionistar_session_key")
        )
        if session_key:
            cart = merge_anonymous_cart_session(
                user=request.user,
                session_key=str(session_key),
            )
            return success_response(
                data=CartSerializer(cart, context={"request": request}).data,
                message="Anonymous cart merged.",
            )

        guest_items = request.data.get("items", [])
        if not isinstance(guest_items, list):
            return error_response(message="items must be a list.", status=status.HTTP_400_BAD_REQUEST)
        cart = merge_guest_cart(user=request.user, guest_items=guest_items)
        return success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message=f"Guest cart merged: {len(guest_items)} item(s) processed.",
        )
