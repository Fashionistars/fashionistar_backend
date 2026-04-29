"""Cart selectors for read-only DRF and Django-Ninja access."""

from __future__ import annotations

from apps.cart.models import Cart
from apps.common.selectors import BaseSelector


class CartSelector(BaseSelector):
    """Read-only query helpers for the cart domain."""

    model = Cart

    @staticmethod
    def for_user(user):
        """Return the user's cart queryset with related product data loaded."""

        return (
            Cart.objects.filter(user=user)
            .select_related("coupon")
            .prefetch_related(
                "items__product__vendor",
                "items__product__category",
                "items__product__brand",
                "items__variant__size",
                "items__variant__color",
            )
        )

    @staticmethod
    async def aget_for_user_or_none(user) -> Cart | None:
        """Async: return a user's cart without creating one."""

        try:
            return await CartSelector.for_user(user).aget()
        except Cart.DoesNotExist:
            return None
