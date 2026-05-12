# apps/cart/selectors.py
"""
Cart Domain Selectors — Read-only data fetching layer.

Architecture Rules (NON-NEGOTIABLE):
  ─ Selectors NEVER mutate data. All mutations live in services/.
  ─ Sync class methods → used in DRF sync views / admin.
  ─ Async methods (prefix `a`) → used in Django-Ninja async views.
  ─ ZERO sync_to_async() usage.
  ─ All async methods use Django 6.0 native async ORM:
      aget(), acount(), aexists(), aaggregate()
      [row async for row in qs]  ← async QuerySet iteration
      prefetch_related_objects([obj], ...)  ← async prefetch after aget()

Reverse FK traversals from Cart model:
  cart.items         → CartItem rows (related_name="items")
  cart.activity_logs → CartActivityLog rows (related_name="activity_logs")

Reverse FK traversals from CartItem model:
  item.product       → Product (FK)
  item.variant       → ProductVariant (FK, nullable)
  item.cart          → parent Cart
"""

from __future__ import annotations

import logging
from typing import Any

from decimal import Decimal

from django.db.models import Prefetch
from django.db.models import aprefetch_related_objects

from apps.cart.models import Cart, CartActivityLog, CartItem
from apps.common.selectors import BaseSelector

logger = logging.getLogger(__name__)


class CartSelector(BaseSelector):
    """
    Read-only query helpers for the cart domain.

    All sync methods are safe for DRF sync views and Django admin.
    All async methods use Django 6.0 native async ORM — zero sync_to_async.
    """

    model = Cart

    # ─────────────────────────────────────────────────────────────────
    # SYNC — DRF views, admin, management commands
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def for_user(user):
        """
        Return the authenticated user's cart queryset with full item prefetch.

        Prefetches items → product (vendor, categories) + variant (size, color)
        to eliminate N+1 queries in DRF serializers.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            QuerySet[Cart] filtered by user.
        """
        return (
            Cart.objects.filter(user=user)
            .select_related("coupon")
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=CartItem.objects.filter(is_saved_for_later=False)
                    .select_related(
                        "product__vendor",
                        "variant__size",
                        "variant__color",
                    )
                    .prefetch_related("product__categories", "product__sub_categories")
                    .order_by("created_at"),
                ),
            )
        )

    @staticmethod
    def for_session_key(session_key: str):
        """
        Return an anonymous session cart queryset with full item prefetch.

        Args:
            session_key: Frontend-generated UUID (fashionistar_session_key).

        Returns:
            QuerySet[Cart] filtered by session_key and no user.
        """
        return (
            Cart.objects.filter(user__isnull=True, session_key=session_key)
            .select_related("coupon")
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=CartItem.objects.filter(is_saved_for_later=False)
                    .select_related(
                        "product__vendor",
                        "variant__size",
                        "variant__color",
                    )
                    .prefetch_related("product__categories", "product__sub_categories")
                    .order_by("created_at"),
                ),
            )
        )

    @staticmethod
    def for_identity(*, user=None, session_key: str | None = None):
        """
        Return the cart queryset for either authenticated or anonymous owner.

        Args:
            user: Optional authenticated user.
            session_key: Optional anonymous session key.

        Returns:
            QuerySet[Cart] — empty queryset if neither owner is provided.
        """
        if user is not None and getattr(user, "is_authenticated", False):
            return CartSelector.for_user(user)
        if session_key:
            return CartSelector.for_session_key(session_key)
        return Cart.objects.none()

    # ─────────────────────────────────────────────────────────────────
    # ASYNC — Django-Ninja async reads (Django 6.0 native ORM only)
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def aget_for_identity_or_none(
        *,
        user=None,
        session_key: str | None = None,
    ) -> Cart | None:
        """
        Async: return a cart for user/session without creating one.

        Uses aget() for the single-row ownership lookup.
        Returns None if the cart does not exist.

        Args:
            user: Optional authenticated user.
            session_key: Optional anonymous session key.

        Returns:
            Cart instance or None.
        """
        try:
            return (
                await CartSelector.for_identity(
                    user=user,
                    session_key=session_key,
                )
                .select_related("coupon")
                .aget()
            )
        except Cart.DoesNotExist:
            return None

    @staticmethod
    async def aget_for_user_or_none(user) -> Cart | None:
        """
        Async: return the authenticated user's cart without creating one.

        Args:
            user: Authenticated UnifiedUser instance.

        Returns:
            Cart instance or None.
        """
        return await CartSelector.aget_for_identity_or_none(user=user)

    @staticmethod
    async def aget_cart_with_items(
        *,
        user=None,
        session_key: str | None = None,
    ) -> Cart | None:
        """
        Async: return a fully prefetched cart with active line items.

        Uses aget() + aprefetch_related_objects() to load items, their
        products, variants, and gallery media in separate async queries
        (no sync_to_async).

        Prefetch path:
          cart.items → CartItem → product (vendor, categories) → variant (size, color)

        Args:
            user: Optional authenticated user.
            session_key: Optional anonymous session key.

        Returns:
            Cart instance with items prefetched, or None if no cart exists.
        """
        try:
            if user is not None and getattr(user, "is_authenticated", False):
                cart = await Cart.objects.select_related("coupon").aget(user=user)
            elif session_key:
                cart = await Cart.objects.select_related("coupon").aget(
                    user__isnull=True, session_key=session_key
                )
            else:
                return None

            await aprefetch_related_objects(
                [cart],
                Prefetch(
                    "items",
                    queryset=CartItem.objects.filter(is_saved_for_later=False)
                    .select_related(
                        "product__vendor",
                        "variant__size",
                        "variant__color",
                    )
                    .prefetch_related("product__categories", "product__sub_categories")
                    .order_by("created_at"),
                ),
            )
            return cart
        except Cart.DoesNotExist:
            return None
        except Exception as exc:
            logger.error("aget_cart_with_items: %s", exc)
            return None

    @staticmethod
    async def aget_cart_summary(
        *,
        user=None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Async: return a lightweight cart summary dict for Ninja badge/header rendering.

        Uses aaggregate() for a single-query SUM of line totals.
        No model instance is hydrated — only plain dict is returned.

        Returns:
            dict with keys: item_count, subtotal, coupon_discount, total, currency,
                            coupon_code (str or None).
        """
        empty = {
            "item_count": 0,
            "subtotal": "0.00",
            "coupon_discount": "0.00",
            "total": "0.00",
            "currency": "NGN",
            "coupon_code": None,
        }
        try:
            # Identify the cart row
            if user is not None and getattr(user, "is_authenticated", False):
                cart_qs = Cart.objects.filter(user=user).select_related("coupon")
            elif session_key:
                cart_qs = Cart.objects.filter(
                    user__isnull=True, session_key=session_key
                ).select_related("coupon")
            else:
                return empty

            cart = await cart_qs.aget()

            summary = await cart.aget_summary_from_db()
            subtotal = summary["subtotal"] or Decimal("0")
            discount = summary["coupon_discount"] or Decimal("0")
            total = summary["total"] or Decimal("0")

            return {
                "item_count": summary["item_count"] or 0,
                "subtotal": str(subtotal.quantize(Decimal("0.01"))),
                "coupon_discount": str(discount.quantize(Decimal("0.01"))),
                "total": str(total.quantize(Decimal("0.01"))),
                "currency": summary["currency"],
                "coupon_code": summary["coupon_code"],
            }
        except Cart.DoesNotExist:
            return empty
        except Exception as exc:
            logger.error("aget_cart_summary: %s", exc)
            return empty

    @staticmethod
    async def aget_cart_item_count(
        *,
        user=None,
        session_key: str | None = None,
    ) -> int:
        """
        Async: return the integer count of active cart items.

        Designed for navigation badge rendering — one acount() query.
        Zero model instantiation, zero sync_to_async.

        Args:
            user: Optional authenticated user.
            session_key: Optional anonymous session key.

        Returns:
            int — number of active (not saved for later) cart items.
        """
        try:
            if user is not None and getattr(user, "is_authenticated", False):
                cart_filter = {"cart__user": user}
            elif session_key:
                cart_filter = {
                    "cart__user__isnull": True,
                    "cart__session_key": session_key,
                }
            else:
                return 0
            cart = await Cart.objects.only("id").aget(**{
                key.removeprefix("cart__"): value for key, value in cart_filter.items()
            })
            return await cart.aget_item_count_from_db()
        except Exception as exc:
            logger.error("aget_cart_item_count: %s", exc)
            return 0

    @staticmethod
    async def aget_saved_for_later_items(
        *,
        user=None,
        session_key: str | None = None,
    ) -> list[dict]:
        """
        Async: return items the user has saved for later (not in active cart).

        Uses async iteration over .values() — zero sync_to_async.

        Args:
            user: Optional authenticated user.
            session_key: Optional anonymous session key.

        Returns:
            list[dict] with item_id, product title, price, and thumbnail.
        """
        try:
            if user is not None and getattr(user, "is_authenticated", False):
                cart_filter = {"cart__user": user}
            elif session_key:
                cart_filter = {
                    "cart__user__isnull": True,
                    "cart__session_key": session_key,
                }
            else:
                return []
            cart = await Cart.objects.only("id").aget(**{
                key.removeprefix("cart__"): value for key, value in cart_filter.items()
            })
            return await cart.alist_saved_for_later_from_db()
        except Exception as exc:
            logger.error("aget_saved_for_later_items: %s", exc)
            return []

    @staticmethod
    async def aget_cart_activity_log(
        *,
        user=None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Async: return cart activity log entries for analytics and support views.

        Traversal: cart.activity_logs reverse FK (related_name="activity_logs").
        Uses async iteration over .values() — zero sync_to_async.

        Args:
            user: Authenticated user (anonymous carts not tracked here).
            limit: Max number of log entries to return (default 20).

        Returns:
            list[dict] with action, product title, quantity, metadata, created_at.
        """
        try:
            if user is None or not getattr(user, "is_authenticated", False):
                return []
            cart = await Cart.objects.only("id").aget(user=user)
            return await cart.alist_activity_from_db(limit=limit)
        except Exception as exc:
            logger.error("aget_cart_activity_log user=%s: %s", user, exc)
            return []
