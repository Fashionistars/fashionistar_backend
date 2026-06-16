# apps/product/services/__init__.py
from apps.product.services.product_service import (
    create_product,
    update_product,
    publish_product,
    approve_product,
    reject_product,
    archive_product,
    attach_gallery_media,
    remove_gallery_media,
    adjust_inventory,
    create_review,
    merge_anonymous_wishlist_session,
    toggle_wishlist,
    validate_coupon,
    validate_and_apply_coupon,
    redeem_coupon,
)
    
from apps.product.services.product_draft import (
    create_draft_session,
    update_draft_session,
    discard_draft_session,
    commit_draft_session,
)



from apps.product.services.async_product_service import (
    async_create_review,
    async_create_review_for_slug,
    async_increment_product_views,
    async_record_product_view,
    async_toggle_wishlist,
    async_toggle_wishlist_for_slug,
    async_adjust_inventory,
    async_validate_and_apply_coupon,
)

__all__ = [
    # Sync service functions
    "create_product",
    "update_product",
    "publish_product",
    "approve_product",
    "reject_product",
    "archive_product",
    "attach_gallery_media",
    "remove_gallery_media",
    "adjust_inventory",
    "create_review",
    "merge_anonymous_wishlist_session",
    "toggle_wishlist",
    "validate_coupon",
    "validate_and_apply_coupon",
    "redeem_coupon",
    "create_draft_session",
    "update_draft_session",
    "discard_draft_session",
    "commit_draft_session",
    # Async service wrappers
    "async_create_review",
    "async_create_review_for_slug",
    "async_increment_product_views",
    "async_record_product_view",
    "async_toggle_wishlist",
    "async_toggle_wishlist_for_slug",
    "async_adjust_inventory",
    "async_validate_and_apply_coupon",
]
