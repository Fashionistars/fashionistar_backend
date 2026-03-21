# apps/common/utils/cloudinary_metadata.py
"""
Cloudinary webhook metadata extraction and validation.

Parses the public_id from Cloudinary to extract:
  - Asset type (image vs video)
  - User role (customer, vendor, admin)
  - Model target (avatar, product_image, category_image, etc)
  - User/Model ID for database routing

Public ID Structure (convention):
    /avatars/user_{uuid}/                  → UnifiedUser.avatar
    /products/images/{product_id}/         → Product.image
    /products/gallery/{gallery_id}/        → Gallery.image
    /vendors/images/{vendor_id}/           → Vendor.avatar
    /categories/images/{category_id}/      → Category.image
    /brands/images/{brand_id}/             → Brand.image
    /collections/images/{collection_id}/   → Collections.image
    /admin/uploads/{admin_id}/             → Admin user profile/uploads
    
Asset types can be inferred from:
  - Cloudinary resource_type: "image", "video", etc
  - File extension: .jpg, .mp4, etc
  - Eager transformations: video assets have different eager configs
"""

from __future__ import annotations

import logging
import re
import uuid as uuid_lib
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class AssetType(str, Enum):
    """Cloudinary asset media type."""
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class UserRole(str, Enum):
    """User role inferred from path structure."""
    CUSTOMER = "customer"
    VENDOR = "vendor"
    ADMIN = "admin"
    STAFF = "staff"
    SUPPORT = "support"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class ModelTarget(str, Enum):
    """Target Django model for webhook routing."""
    AVATAR = "avatar"
    PRODUCT_IMAGE = "product_image"
    PRODUCT_VIDEO = "product_video"
    PRODUCT_GALLERY = "product_gallery"
    PRODUCT_COLOR = "product_color"
    VENDOR_AVATAR = "vendor_avatar"
    VENDOR_BANNER = "vendor_banner"
    CATEGORY_IMAGE = "category_image"
    BRAND_IMAGE = "brand_image"
    COLLECTION_IMAGE = "collection_image"
    MEASUREMENT = "measurement"
    BLOG_IMAGE = "blog_image"
    ADMIN_UPLOAD = "admin_upload"
    UNKNOWN = "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PublicIDMetadata:
    """
    Extracted metadata from Cloudinary public_id.
    
    Attributes:
        full_path: Complete public_id string from Cloudinary
        asset_type: IMAGE, VIDEO, DOCUMENT, or UNKNOWN
        user_role: CUSTOMER, VENDOR, ADMIN, SYSTEM, or UNKNOWN
        model_target: Target Django model for webhook routing
        user_id: Extracted user/entity ID (needed for DB lookup)
        folder_path: Folder structure (e.g., "avatars/user_abc123")
        filename: Base filename without extension
        is_valid: Whether this metadata is usable for routing
        error_message: Reason for invalidity, if any
    """
    
    full_path: str
    asset_type: AssetType
    user_role: UserRole
    model_target: ModelTarget
    user_id: Optional[str] = None
    folder_path: Optional[str] = None
    filename: Optional[str] = None
    is_valid: bool = True
    error_message: Optional[str] = None
    
    def __str__(self) -> str:
        """Human-readable representation."""
        return (
            f"PublicIDMetadata(path={self.full_path!r}, "
            f"asset={self.asset_type.value}, role={self.user_role.value}, "
            f"model={self.model_target.value}, user_id={self.user_id})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# PARSER
# ─────────────────────────────────────────────────────────────────────────────

class CloudinaryPublicIDParser:
    """
    Parse Cloudinary public_id to extract metadata for webhook routing.
    
    Uses path-based convention to identify:
      - Asset type (image vs video)
      - User role (customer vs vendor vs admin)
      - Model target (which Django model)
      - Entity ID (for database lookup)
    
    Defensive parsing: if structure doesn't match convention,
    returns metadata with is_valid=False for manual review.
    """
    
    # Regex patterns for common folder structures
    PATTERNS = {
        "avatar_customer": re.compile(
            r"^/avatars/user_([a-f0-9\-]+)/?",
            re.IGNORECASE
        ),
        "product_image": re.compile(
            r"^/products/images/([a-zA-Z0-9\-_]+)/?",
            re.IGNORECASE
        ),
        "product_gallery": re.compile(
            r"^/products/gallery/([a-zA-Z0-9\-_]+)/?",
            re.IGNORECASE
        ),
        "product_color": re.compile(
            r"^/products/colors/([a-zA-Z0-9\-_]+)/?",
            re.IGNORECASE
        ),
        "vendor_avatar": re.compile(
            r"^/vendors/images/([a-zA-Z0-9\-_]+)/?",
            re.IGNORECASE
        ),
        "category_image": re.compile(
            r"^/categories/images/([a-zA-Z0-9\-_]+)/?",
            re.IGNORECASE
        ),
        "brand_image": re.compile(
            r"^/brands/images/([a-zA-Z0-9\-_]+)/?",
            re.IGNORECASE
        ),
        "collection_image": re.compile(
            r"^/collections/images/([a-zA-Z0-9\-_]+)/?",
            re.IGNORECASE
        ),
        "blog_image": re.compile(
            r"^/blogs/images/([a-zA-Z0-9\-_]+)/?",
            re.IGNORECASE
        ),
        "measurement": re.compile(
            r"^/measurements/([a-zA-Z0-9\-_]+)/?",
            re.IGNORECASE
        ),
    }
    
    @classmethod
    def parse(
        cls,
        public_id: str,
        resource_type: Optional[str] = None,
        eager_list: Optional[list] = None,
    ) -> PublicIDMetadata:
        """
        Parse public_id and extract metadata.
        
        Args:
            public_id: Cloudinary public_id (includes folder path)
            resource_type: Optional resource_type from Cloudinary API
                          ('image', 'video', etc) — if provided, trusted
            eager_list: Optional list of eager transformations
                       (helps differentiate image vs video)
        
        Returns:
            PublicIDMetadata with extracted fields
        """
        
        if not public_id:
            return PublicIDMetadata(
                full_path=public_id or "",
                asset_type=AssetType.UNKNOWN,
                user_role=UserRole.UNKNOWN,
                model_target=ModelTarget.UNKNOWN,
                is_valid=False,
                error_message="Empty public_id",
            )
        
        # Determine asset type
        asset_type = cls._determine_asset_type(public_id, resource_type, eager_list)
        
        # Match against patterns
        for pattern_name, pattern in cls.PATTERNS.items():
            match = pattern.match(public_id)
            if match:
                user_id = match.group(1)
                user_role, model_target = cls._map_pattern_to_role_and_model(
                    pattern_name, asset_type
                )
                
                return PublicIDMetadata(
                    full_path=public_id,
                    asset_type=asset_type,
                    user_role=user_role,
                    model_target=model_target,
                    user_id=user_id,
                    folder_path=public_id.rsplit("/", 1)[0] if "/" in public_id else public_id,
                    filename=public_id.rsplit("/", 1)[-1],
                    is_valid=True,
                )
        
        # No pattern matched
        logger.warning(
            "CloudinaryPublicIDParser: unrecognized public_id format: %s",
            public_id,
        )
        return PublicIDMetadata(
            full_path=public_id,
            asset_type=asset_type,
            user_role=UserRole.UNKNOWN,
            model_target=ModelTarget.UNKNOWN,
            folder_path=public_id.rsplit("/", 1)[0] if "/" in public_id else public_id,
            filename=public_id.rsplit("/", 1)[-1],
            is_valid=False,
            error_message=f"Unrecognized public_id format: {public_id}",
        )
    
    @staticmethod
    def _determine_asset_type(
        public_id: str,
        resource_type: Optional[str] = None,
        eager_list: Optional[list] = None,
    ) -> AssetType:
        """Determine asset type: image, video, or document."""
        
        # If resource_type provided by Cloudinary, trust it
        if resource_type:
            if resource_type.lower() == "video":
                return AssetType.VIDEO
            elif resource_type.lower() in ("image", "upload"):
                return AssetType.IMAGE
            elif resource_type.lower() in ("raw", "auto"):
                return AssetType.DOCUMENT
        
        # Fall back to extension-based detection
        extension = public_id.rsplit(".", 1)[-1].lower() if "." in public_id else ""
        
        video_ext = {"mp4", "webm", "mov", "avi", "mkv", "flv", "m3u8"}
        image_ext = {"jpg", "jpeg", "png", "gif", "webp", "avif", "svg", "ico", "bmp"}
        
        if extension in video_ext:
            return AssetType.VIDEO
        elif extension in image_ext:
            return AssetType.IMAGE
        elif extension in {"pdf", "doc", "docx", "txt", "zip"}:
            return AssetType.DOCUMENT
        
        # Check eager transformations: video eager configs are rare
        if eager_list and len(eager_list) > 0:
            # Most eager transforms are image-related (crop, resize, quality, etc)
            # Video-specific eager transforms have "streaming_profile" or codec
            for eager in eager_list:
                if isinstance(eager, dict):
                    eager_str = str(eager).lower()
                    if any(x in eager_str for x in ["streaming_profile", "codec", "duration"]):
                        return AssetType.VIDEO
            return AssetType.IMAGE
        
        # Default to IMAGE for unknown
        return AssetType.IMAGE
    
    @staticmethod
    def _map_pattern_to_role_and_model(
        pattern_name: str,
        asset_type: AssetType,
    ) -> tuple[UserRole, ModelTarget]:
        """Map regex pattern name to user role and model target."""
        
        mapping = {
            "avatar_customer": (UserRole.CUSTOMER, ModelTarget.AVATAR),
            "product_image": (UserRole.VENDOR, ModelTarget.PRODUCT_IMAGE),
            "product_gallery": (UserRole.VENDOR, ModelTarget.PRODUCT_GALLERY),
            "product_color": (UserRole.VENDOR, ModelTarget.PRODUCT_COLOR),
            "vendor_avatar": (UserRole.VENDOR, ModelTarget.VENDOR_AVATAR),
            "category_image": (UserRole.ADMIN, ModelTarget.CATEGORY_IMAGE),
            "brand_image": (UserRole.ADMIN, ModelTarget.BRAND_IMAGE),
            "collection_image": (UserRole.ADMIN, ModelTarget.COLLECTION_IMAGE),
            "blog_image": (UserRole.ADMIN, ModelTarget.BLOG_IMAGE),
            "measurement": (UserRole.CUSTOMER, ModelTarget.MEASUREMENT),
        }
        
        user_role, model_target = mapping.get(
            pattern_name,
            (UserRole.UNKNOWN, ModelTarget.UNKNOWN),
        )
        
        # Adjust model_target for video assets
        if asset_type == AssetType.VIDEO:
            if model_target == ModelTarget.PRODUCT_IMAGE:
                model_target = ModelTarget.PRODUCT_VIDEO
        
        return user_role, model_target


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def parse_cloudinary_public_id(
    public_id: str,
    resource_type: Optional[str] = None,
    eager_list: Optional[list] = None,
) -> PublicIDMetadata:
    """
    Parse Cloudinary public_id to extract routing metadata.
    
    This is the main public API for webhook routing.
    
    Args:
        public_id: Cloudinary public_id string
        resource_type: Optional resource_type from Cloudinary webhook
        eager_list: Optional eager transformations list
    
    Returns:
        PublicIDMetadata for database routing and logging
    
    Example:
        >>> metadata = parse_cloudinary_public_id(
        ...     "/avatars/user_550e8400-e29b-41d4-a716-446655440000/avatar.jpg",
        ...     resource_type="image"
        ... )
        >>> metadata.model_target
        <ModelTarget.AVATAR: 'avatar'>
        >>> metadata.is_valid
        True
    """
    return CloudinaryPublicIDParser.parse(public_id, resource_type, eager_list)
