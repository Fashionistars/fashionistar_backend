# apps/common/utils/webhook_idempotency.py
"""
Cloudinary webhook idempotency management.

Prevents duplicate webhook processing by:
  1. Generating deterministic idempotency keys
  2. Checking Redis cache for recent processing
  3. Recording processed webhooks in database for audit trail
  4. Handling distributed scenarios (multiple workers)

Design:
  - Idempotency Key = SHA256(public_id + timestamp + asset_type)
  - Storage: Redis (fast, < 1ms lookup) + Database (audit trail)
  - TTL: 1 hour (webhooks retry within minutes)
  - Immutable once marked processed (prevents double-processing)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta
from typing import Optional

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Cache key prefix for idempotency tracking
_IDEMPOTENCY_KEY_PREFIX = "webhook:idempotency:"
_IDEMPOTENCY_TTL = 3600  # 1 hour


# ─────────────────────────────────────────────────────────────────────────────
# IDEMPOTENCY KEY GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_idempotency_key(
    public_id: str,
    timestamp: str,
    asset_type: str,
) -> str:
    """
    Generate deterministic idempotency key.
    
    Same inputs always produce same key, enabling duplicate detection.
    
    Args:
        public_id: Cloudinary public_id
        timestamp: X-Cld-Timestamp header from webhook
        asset_type: image, video, or document
    
    Returns:
        Hex-encoded SHA256 hash (64 chars)
    
    Example:
        >>> key = generate_idempotency_key("/avatars/user_xyz", "1234567890", "image")
        >>> key
        'a1b2c3d4e5f6...'  # 64-char hex string
    """
    
    payload = f"{public_id}|{timestamp}|{asset_type}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# DUPLICATE DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def is_duplicate(
    idempotency_key: str,
    check_database: bool = False,
) -> bool:
    """
    Check if webhook has already been processed.
    
    Fast path: Redis cache (< 1ms latency)
    Slow path: Database query (if Redis cache miss)
    
    Args:
        idempotency_key: SHA256 hash from generate_idempotency_key()
        check_database: Also check database (slower but more reliable)
    
    Returns:
        True if duplicate (already processed), False if new
    
    Example:
        >>> is_duplicate("a1b2c3d4e5f6...")
        False  # First time seeing this key
        >>> is_duplicate("a1b2c3d4e5f6...")
        True  # Duplicate detected!
    """
    
    cache_key = f"{_IDEMPOTENCY_KEY_PREFIX}{idempotency_key}"
    
    # Check Redis cache (fast path)
    cached  = cache.get(cache_key)
    if cached is not None:
        logger.debug("Duplicate webhook detected via cache: %s", idempotency_key[:16])
        return True
    
    # Check database (slow path) if requested
    if check_database:
        try:
            from apps.common.models.processed_webhook import CloudinaryProcessedWebhook
            
            exists = CloudinaryProcessedWebhook.objects.filter(
                idempotency_key=idempotency_key
            ).exists()
            
            if exists:
                logger.debug(
                    "Duplicate webhook detected via database: %s",
                    idempotency_key[:16]
                )
                # Also cache it for speed
                cache.set(cache_key, True, _IDEMPOTENCY_TTL)
                return True
        except Exception as exc:
            logger.warning(
                "Database check failed for idempotency: %s — proceeding to process",
                exc,
            )
    
    return False


# ─────────────────────────────────────────────────────────────────────────────
# RECORDING PROCESSED WEBHOOKS
# ─────────────────────────────────────────────────────────────────────────────

def mark_processed(
    idempotency_key: str,
    public_id: str,
    asset_type: str,
    model_target: str,
    model_pk: Optional[str] = None,
    secure_url: Optional[str] = None,
    processing_time_ms: float = 0.0,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """
    Record webhook as processed in Redis and database.
    
    Called AFTER successful processing to prevent future re-processing.
    Also serves as audit trail for webhook history.
    
    Args:
        idempotency_key: SHA256 hash from generate_idempotency_key()
        public_id: Cloudinary public_id
        asset_type: image, video, or document
        model_target: Target Django model (avatar, product, etc)
        model_pk: PK of the updated model instance
        secure_url: Cloudinary secure_url that was saved
        processing_time_ms: How long processing took
        success: Whether processing succeeded
        error_message: Error message if processing failed
    
    Returns:
        None (side effects: Redis cache + database write)
    
    Example:
        >>> mark_processed(
        ...     idempotency_key="a1b2c3...",
        ...     public_id="/avatars/user_xyz/avatar.jpg",
        ...     asset_type="image",
        ...     model_target="avatar",
        ...     model_pk="550e8400-e29b-41d4-a716-446655440000",
        ...     success=True,
        ... )
    """
    
    cache_key = f"{_IDEMPOTENCY_KEY_PREFIX}{idempotency_key}"
    
    # Mark in cache (fast, immediate)
    cache.set(cache_key, True, _IDEMPOTENCY_TTL)
    logger.debug("Webhook marked processed in cache: %s", idempotency_key[:16])
    
    # Record in database (audit trail)
    try:
        from apps.common.models.processed_webhook import CloudinaryProcessedWebhook
        
        CloudinaryProcessedWebhook.objects.create(
            idempotency_key=idempotency_key,
            public_id=public_id,
            asset_type=asset_type,
            model_target=model_target,
            model_pk=model_pk or "",
            secure_url=secure_url or "",
            processing_time_ms=processing_time_ms,
            success=success,
            error_message=error_message,
            payload_hash=hashlib.sha256(
                f"{public_id}|{asset_type}|{model_target}".encode("utf-8")
            ).hexdigest(),
        )
        
        logger.info(
            "Webhook recorded in ProcessedWebhook: %s (%s) → %s.%s",
            idempotency_key[:16],
            "✓" if success else "✗",
            model_target,
            model_pk,
        )
    except Exception as exc:
        logger.error(
            "Failed to record processed webhook in database: %s — %s",
            idempotency_key[:16],
            exc,
        )
        # Don't re-raise — we already marked it in Redis


# ─────────────────────────────────────────────────────────────────────────────
# WEBHOOK REPLAY FOR DEBUGGING
# ─────────────────────────────────────────────────────────────────────────────

def get_processed_webhook_details(
    idempotency_key: Optional[str] = None,
    public_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Retrieve details of a previously-processed webhook.
    
    Useful for debugging and for admin dashboard.
    
    Args:
        idempotency_key: Look up by idempotency key (fast)
        public_id: Look up by public_id (slower, but human-readable)
    
    Returns:
        Dictionary with webhook details, or None if not found
    
    Example:
        >>> details = get_processed_webhook_details(
        ...     idempotency_key="a1b2c3d4e5f6..."
        ... )
        >>> details["model_target"]
        "avatar"
        >>> details["success"]
        True
    """
    
    try:
        from apps.common.models.processed_webhook import CloudinaryProcessedWebhook
        
        if idempotency_key:
            webhook = CloudinaryProcessedWebhook.objects.filter(
                idempotency_key=idempotency_key
            ).first()
        elif public_id:
            webhook = CloudinaryProcessedWebhook.objects.filter(
                public_id=public_id
            ).order_by("-processed_at").first()
        else:
            return None
        
        if webhook:
            return {
                "idempotency_key": webhook.idempotency_key,
                "public_id": webhook.public_id,
                "asset_type": webhook.asset_type,
                "model_target": webhook.model_target,
                "model_pk": webhook.model_pk,
                "secure_url": webhook.secure_url,
                "success": webhook.success,
                "error_message": webhook.error_message,
                "processing_time_ms": webhook.processing_time_ms,
                "processed_at": webhook.processed_at.isoformat(),
            }
    except Exception as exc:
        logger.error("Failed to retrieve processed webhook details: %s", exc)
    
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CLEANUP (for testing and data retention)
# ─────────────────────────────────────────────────────────────────────────────

def cleanup_old_processed_webhooks(
    older_than_hours: int = 24,
    dry_run: bool = False,
) -> int:
    """
    Remove old webhook processing records.
    
    Used for:
      - Test cleanup
      - Data retention policy
      - Storage optimization
    
    Args:
        older_than_hours: Delete records older than this many hours
        dry_run: If True, don't actually delete (just count)
    
    Returns:
        Number of records deleted (or that would be deleted if dry_run=True)
    
    Example:
        >>> deleted = cleanup_old_processed_webhooks(older_than_hours=72)
        >>> print(f"Deleted {deleted} old webhooks")
    """
    
    try:
        from apps.common.models.processed_webhook import CloudinaryProcessedWebhook
        
        cutoff_time = timezone.now() - timedelta(hours=older_than_hours)
        query = CloudinaryProcessedWebhook.objects.filter(
            processed_at__lt=cutoff_time
        )
        
        count = query.count()
        
        if not dry_run:
            query.delete()
            logger.info(
                "Cleaned up %d old processed webhooks (older than %d hours)",
                count,
                older_than_hours,
            )
        else:
            logger.info(
                "DRY RUN: Would delete %d old processed webhooks (older than %d hours)",
                count,
                older_than_hours,
            )
        
        return count
    except Exception as exc:
        logger.error("Failed to cleanup old processed webhooks: %s", exc)
        return 0
