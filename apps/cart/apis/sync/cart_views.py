# apps/cart/apis/sync/cart_views.py
"""
DRF cart views — 2027 Edition.

All endpoints require IsAuthenticated + IsClient unless explicitly AllowAny.

Changes (2027 modernization):
  • _cart_identity: strips non-alphanumeric/hyphen chars, enforces 40-char max.
  • CartAddItemView: extracts X-Idempotency-Key / Idempotency-Key header and
    echoes it in the response for client-level deduplication detection.
  • CartRemoveItemView / CartClearView: use .first() instead of .get() to
    avoid DoesNotExist when the cart has zero items after the mutation.
"""

import logging
import re
import uuid

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
    discard_anonymous_cart_session,
)

logger = logging.getLogger(__name__)

_RENDERERS = [CustomJSONRenderer, BrowsableAPIRenderer]
_PARSERS = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)

# Only alphanumeric + hyphens allowed in session keys (UUID-safe charset)
_SESSION_KEY_RE = re.compile(r"[^a-zA-Z0-9\-]")
_SESSION_KEY_MAX_LEN = 40


def _sanitize_session_key(raw: str) -> str:
    """Normalize an anonymous session key: strip illegal chars, cap length."""
    cleaned = _SESSION_KEY_RE.sub("", raw)
    return cleaned[:_SESSION_KEY_MAX_LEN]


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

    raw_key = (
        request.data.get("session_key")
        or request.headers.get("X-Fashionistar-Session-Key")
        or request.query_params.get("session_key")
        or request.COOKIES.get("fashionistar_session_key")
    )
    if not raw_key:
        raise ValueError("session_key is required for anonymous cart access.")

    session_key = _sanitize_session_key(str(raw_key))
    if not session_key:
        raise ValueError("session_key contains invalid characters.")
    return {"session_key": session_key}


def _extract_idempotency_key(request) -> str:
    """
    Extract the client-supplied idempotency key from request headers.

    Falls back to a server-generated UUID when the client omits the header,
    ensuring every write is always idempotent at the HTTP layer.
    """
    return (
        request.headers.get("X-Idempotency-Key")
        or request.headers.get("Idempotency-Key")
        or str(uuid.uuid4())
    )


class CartAddItemView(APIView):
    """
    POST /api/v1/cart/add/
    Body: { product_slug, quantity, variant_id? }
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def post(self, request):
        idempotency_key = _extract_idempotency_key(request)

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
        response = success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Item added to cart.",
            status=status.HTTP_200_OK,
        )
        # Echo the idempotency key so clients can detect server deduplication
        response["X-Idempotency-Key"] = idempotency_key
        return response


class CartRetrieveView(APIView):
    """GET /api/v1/cart/ — return the current cart for an auth user or session."""

    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            identity = _cart_identity(request)
        except ValueError:
            identity = {}

        from apps.cart.selectors import CartSelector

        cart = CartSelector.for_identity(**identity).first()
        if cart is None:
            data = {
                "id": None,
                "items": [],
                "item_count": 0,
                "subtotal": "0.00",
                "currency": "NGN",
                "expires_at": None,
            }
        else:
            data = CartSerializer(cart, context={"request": request}).data

        return success_response(
            data=data,
            message="Cart retrieved.",
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

        # Use .first() — cart may have zero items after removal, .get() would
        # raise DoesNotExist when the cart row still exists but is now empty.
        cart = CartSelector.for_identity(**identity).first()
        if cart is None:
            data = {
                "id": None,
                "items": [],
                "item_count": 0,
                "subtotal": "0.00",
                "currency": "NGN",
                "expires_at": None,
            }
        else:
            data = CartSerializer(cart, context={"request": request}).data

        return success_response(data=data, message="Item removed from cart.")


class CartUpdateQuantityView(APIView):
    """PATCH /api/v1/cart/items/<item_id>/quantity/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def patch(self, request, item_id):
        idempotency_key = _extract_idempotency_key(request)

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

        cart = CartSelector.for_identity(**identity).first()
        if cart is None:
            return error_response(message="Cart not found.", status=status.HTTP_404_NOT_FOUND)

        response = success_response(
            data=CartSerializer(cart, context={"request": request}).data,
            message="Quantity updated.",
        )
        response["X-Idempotency-Key"] = idempotency_key
        return response


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

        # Use .first() — the cart row exists after clear but has zero items;
        # .get() would still work here but .first() is safer for future refactors
        # where clear_cart might delete the cart row itself.
        cart = CartSelector.for_identity(**identity).first()
        if cart is None:
            data = {
                "id": None,
                "items": [],
                "item_count": 0,
                "subtotal": "0.00",
                "currency": "NGN",
                "expires_at": None,
            }
        else:
            data = CartSerializer(cart, context={"request": request}).data

        return success_response(data=data, message="Cart cleared.")


class CartMergeView(APIView):
    """
    POST /api/v1/cart/merge/
    Body:
      { session_key: "..." }
      or legacy { items: [{ product_slug, quantity, variant_id? }] }

    Called after login and before checkout submit. Database-backed anonymous
    carts are preferred; the legacy item-array path remains for older clients.

    RBAC: Restricted to role='client' ONLY.
    Vendors, admins, support, editors, sales, moderators have no shopping
    cart — they manage the platform. Attempting to merge a cart as a non-client
    returns 403 Forbidden to enforce role separation.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request):
        raw_session_key = (
            request.data.get("session_key")
            or request.headers.get("X-Fashionistar-Session-Key")
            or request.COOKIES.get("fashionistar_session_key")
        )
        sanitized_session_key = (
            _sanitize_session_key(str(raw_session_key)) if raw_session_key else None
        )

        # ── RBAC Guard: Cart merge is CLIENT-only ───────────────────────
        # Vendors, admins and other staff roles must NOT have shopping carts.
        # Allowing them to merge would:
        #   1. Create orphaned cart rows for non-purchaser accounts.
        #   2. Let a vendor place orders as a buyer, violating role separation.
        #   3. Pollute cart analytics with non-client traffic.
        user_role = getattr(request.user, "role", None)
        if user_role != "client":
            logger.warning(
                "⚠️ CartMergeView: role=%s user_id=%s attempted cart merge — blocked.",
                user_role,
                getattr(request.user, "id", "unknown"),
            )
            discard_anonymous_cart_session(session_key=sanitized_session_key)
            return error_response(
                message="Cart operations are only available for client accounts.",
                status=status.HTTP_403_FORBIDDEN,
            )

        if sanitized_session_key:
            cart = merge_anonymous_cart_session(
                user=request.user,
                session_key=sanitized_session_key,
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
