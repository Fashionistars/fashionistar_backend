# tests/unit/test_cloudinary_metadata.py
"""
Unit tests for Cloudinary webhook metadata parsing.

Tests:
  - PublicID parsing for various asset types
  - Asset type detection (image vs video)
  - User role inference (customer vs vendor vs admin)
  - Model target mapping
  - Invalid/malformed public_id handling
  - Idempotency key generation
  - Duplicate detection
"""

import pytest
from apps.common.utils.cloudinary_metadata import (
    AssetType,
    UserRole,
    ModelTarget,
    CloudinaryPublicIDParser,
    parse_cloudinary_public_id,
)
from apps.common.utils.webhook_idempotency import (
    generate_idempotency_key,
    is_duplicate,
    mark_processed,
)


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Asset Type Detection
# ─────────────────────────────────────────────────────────────────────────────

class TestAssetTypeDetection:
    """Test asset type detection from public_id, extension, and resource_type."""
    
    def test_asset_type_from_resource_type_image(self):
        """Cloudinary resource_type='image' → AssetType.IMAGE."""
        metadata = parse_cloudinary_public_id(
            "/avatars/user_abc123/avatar.jpg",
            resource_type="image"
        )
        assert metadata.asset_type == AssetType.IMAGE
        assert metadata.is_valid
    
    def test_asset_type_from_resource_type_video(self):
        """Cloudinary resource_type='video' → AssetType.VIDEO."""
        metadata = parse_cloudinary_public_id(
            "/products/images/prod_123/video.mp4",
            resource_type="video"
        )
        assert metadata.asset_type == AssetType.VIDEO
        assert metadata.is_valid
    
    def test_asset_type_from_extension_image(self):
        """Image extension (.jpg, .png, etc) → AssetType.IMAGE."""
        for ext in ["jpg", "png", "gif", "webp", "avif"]:
            metadata = parse_cloudinary_public_id(
                f"/products/images/prod_123/product.{ext}"
            )
            assert metadata.asset_type == AssetType.IMAGE, f"Failed for .{ext}"
    
    def test_asset_type_from_extension_video(self):
        """Video extension (.mp4, .webm, etc) → AssetType.VIDEO."""
        for ext in ["mp4", "webm", "mov", "avi"]:
            metadata = parse_cloudinary_public_id(
                f"/products/images/prod_123/video.{ext}"
            )
            assert metadata.asset_type == AssetType.VIDEO, f"Failed for .{ext}"
    
    def test_asset_type_from_eager_transformations_image(self):
        """Eager transformations without video metadata → IMAGE."""
        eager = [{"width": 800, "crop": "scale"}]
        metadata = parse_cloudinary_public_id(
            "/products/images/prod_123/image",
            eager_list=eager
        )
        assert metadata.asset_type == AssetType.IMAGE
    
    def test_asset_type_from_eager_transformations_video(self):
        """Eager with streaming_profile → AssetType.VIDEO."""
        eager = [{"streaming_profile": "hd"}]
        metadata = parse_cloudinary_public_id(
            "/products/images/prod_123/video",
            eager_list=eager
        )
        assert metadata.asset_type == AssetType.VIDEO


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Public ID Parsing
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicIDParsing:
    """Test parsing of standard public_id formats."""
    
    def test_parse_customer_avatar(self):
        """Customer avatar: /avatars/user_{uuid}/ → CUSTOMER, AVATAR."""
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        metadata = parse_cloudinary_public_id(
            f"/avatars/user_{uuid}/avatar.jpg",
            resource_type="image"
        )
        assert metadata.user_role == UserRole.CUSTOMER
        assert metadata.model_target == ModelTarget.AVATAR
        assert metadata.user_id == uuid
        assert metadata.is_valid
    
    def test_parse_product_image(self):
        """Product image: /products/images/{id}/ → VENDOR, PRODUCT_IMAGE."""
        metadata = parse_cloudinary_public_id(
            "/products/images/prod_xyz123/image.jpg",
            resource_type="image"
        )
        assert metadata.user_role == UserRole.VENDOR
        assert metadata.model_target == ModelTarget.PRODUCT_IMAGE
        assert metadata.user_id == "prod_xyz123"
        assert metadata.is_valid
    
    def test_parse_product_video(self):
        """Product video: /products/images/{id}/ + video → VENDOR, PRODUCT_VIDEO."""
        metadata = parse_cloudinary_public_id(
            "/products/images/prod_xyz123/review.mp4",
            resource_type="video"
        )
        assert metadata.user_role == UserRole.VENDOR
        assert metadata.model_target == ModelTarget.PRODUCT_VIDEO
        assert metadata.is_valid
    
    def test_parse_category_image(self):
        """Category image: /categories/images/{id}/ → ADMIN, CATEGORY_IMAGE."""
        metadata = parse_cloudinary_public_id(
            "/categories/images/cat_456/banner.jpg",
            resource_type="image"
        )
        assert metadata.user_role == UserRole.ADMIN
        assert metadata.model_target == ModelTarget.CATEGORY_IMAGE
        assert metadata.user_id == "cat_456"
        assert metadata.is_valid
    
    def test_parse_vendor_avatar(self):
        """Vendor avatar: /vendors/images/{id}/ → VENDOR, VENDOR_AVATAR."""
        metadata = parse_cloudinary_public_id(
            "/vendors/images/vendor_789/profile.jpg",
            resource_type="image"
        )
        assert metadata.user_role == UserRole.VENDOR
        assert metadata.model_target == ModelTarget.VENDOR_AVATAR
        assert metadata.user_id == "vendor_789"
        assert metadata.is_valid
    
    def test_parse_brand_image(self):
        """Brand image: /brands/images/{id}/ → ADMIN, BRAND_IMAGE."""
        metadata = parse_cloudinary_public_id(
            "/brands/images/brand_001/logo.png",
            resource_type="image"
        )
        assert metadata.user_role == UserRole.ADMIN
        assert metadata.model_target == ModelTarget.BRAND_IMAGE
        assert metadata.is_valid
    
    def test_parse_collection_image(self):
        """Collection image: /collections/images/{id}/ → ADMIN, COLLECTION_IMAGE."""
        metadata = parse_cloudinary_public_id(
            "/collections/images/col_summer/hero.jpg",
            resource_type="image"
        )
        assert metadata.user_role == UserRole.ADMIN
        assert metadata.model_target == ModelTarget.COLLECTION_IMAGE
        assert metadata.is_valid


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Invalid/Malformed Public IDs
# ─────────────────────────────────────────────────────────────────────────────

class TestInvalidPublicIDs:
    """Test handling of malformed or unrecognized public_id formats."""
    
    def test_empty_public_id(self):
        """Empty public_id → invalid."""
        metadata = parse_cloudinary_public_id("")
        assert not metadata.is_valid
        assert metadata.error_message
    
    def test_unrecognized_path_format(self):
        """Unrecognized path structure → invalid but parsed."""
        metadata = parse_cloudinary_public_id(
            "/unknown/path/structure/file.jpg",
            resource_type="image"
        )
        assert not metadata.is_valid
        assert metadata.asset_type == AssetType.IMAGE  # Still detected by extension
        assert metadata.user_role == UserRole.UNKNOWN
    
    def test_missing_id_component(self):
        """Path missing the ID component → invalid."""
        metadata = parse_cloudinary_public_id(
            "/avatars/file.jpg",  # Missing user_XXX
            resource_type="image"
        )
        assert not metadata.is_valid
    
    def test_malformed_uuid(self):
        """Malformed UUID in user_ prefix → still attempts parsing."""
        metadata = parse_cloudinary_public_id(
            "/avatars/user_not-a-valid-uuid/avatar.jpg",
            resource_type="image"
        )
        # Parser extracts the ID anyway, but it's malformed
        assert metadata.user_id == "not-a-valid-uuid"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Idempotency Key Generation
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotencyKeyGeneration:
    """Test deterministic key generation for duplicate detection."""
    
    def test_key_deterministic(self):
        """Same inputs produce same key."""
        key1 = generate_idempotency_key("/avatars/user_abc/avatar.jpg", "1234567890", "image")
        key2 = generate_idempotency_key("/avatars/user_abc/avatar.jpg", "1234567890", "image")
        assert key1 == key2
    
    def test_key_changes_with_public_id(self):
        """Different public_id produces different key."""
        key1 = generate_idempotency_key("/avatars/user_abc/avatar.jpg", "1234567890", "image")
        key2 = generate_idempotency_key("/avatars/user_xyz/avatar.jpg", "1234567890", "image")
        assert key1 != key2
    
    def test_key_changes_with_timestamp(self):
        """Different timestamp produces different key."""
        key1 = generate_idempotency_key("/avatars/user_abc/avatar.jpg", "1234567890", "image")
        key2 = generate_idempotency_key("/avatars/user_abc/avatar.jpg", "1234567891", "image")
        assert key1 != key2
    
    def test_key_length_is_sha256(self):
        """Key is 64-character SHA256 hex string."""
        key = generate_idempotency_key("/avatars/user_abc/avatar.jpg", "1234567890", "image")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Duplicate Detection (requires Redis/cache)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDuplicateDetection:
    """Test idempotency: duplicate webhooks detected and prevented."""
    
    def test_first_webhook_not_duplicate(self):
        """First webhook with new key should not be a duplicate."""
        key = generate_idempotency_key("/avatars/user_abc/avatar.jpg", "1234567890", "image")
        assert not is_duplicate(key)
    
    def test_second_webhook_is_duplicate(self):
        """After marking processed, same key is duplicate."""
        key = generate_idempotency_key("/avatars/user_abc/avatar.jpg", "1234567890", "image")
        
        # Mark as processed
        mark_processed(
            idempotency_key=key,
            public_id="/avatars/user_abc/avatar.jpg",
            asset_type="image",
            model_target="avatar",
            model_pk="550e8400-e29b-41d4-a716-446655440000",
            secure_url="https://res.cloudinary.com/...",
            success=True,
        )
        
        # Should now be detected as duplicate
        assert is_duplicate(key)
    
    def test_different_key_not_duplicate(self):
        """Different idempotency key should not be a duplicate."""
        key1 = generate_idempotency_key("/avatars/user_abc/avatar.jpg", "1234567890", "image")
        key2 = generate_idempotency_key("/avatars/user_xyz/avatar.jpg", "1234567890", "image")
        
        mark_processed(
            idempotency_key=key1,
            public_id="/avatars/user_abc/avatar.jpg",
            asset_type="image",
            model_target="avatar",
            success=True,
        )
        
        # key2 should NOT be a duplicate (different from key1)
        assert not is_duplicate(key2)


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Edge Cases & Security
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and security considerations."""
    
    def test_public_id_with_special_characters(self):
        """Public IDs with URL-safe special characters."""
        metadata = parse_cloudinary_public_id(
            "/products/images/prod_abc-123_xyz/image.jpg",
            resource_type="image"
        )
        assert metadata.user_id == "prod_abc-123_xyz"
        assert metadata.is_valid
    
    def test_case_insensitive_extension_detection(self):
        """Asset type detection should be case-insensitive."""
        metadata1 = parse_cloudinary_public_id("/products/images/p1/image.JPG")
        metadata2 = parse_cloudinary_public_id("/products/images/p1/image.jpg")
        assert metadata1.asset_type == metadata2.asset_type
    
    def test_path_with_trailing_slash(self):
        """Public IDs with trailing slashes should be parsed correctly."""
        metadata = parse_cloudinary_public_id(
            "/avatars/user_abc123/",
            resource_type="image"
        )
        assert metadata.user_role == UserRole.CUSTOMER
        assert metadata.is_valid
    
    def test_str_and_repr_methods(self):
        """Metadata objects have useful string representations."""
        metadata = parse_cloudinary_public_id(
            "/avatars/user_abc/avatar.jpg",
            resource_type="image"
        )
        s = str(metadata)
        r = repr(metadata)
        assert "avatar" in s.lower()
        assert "customer" in s.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
