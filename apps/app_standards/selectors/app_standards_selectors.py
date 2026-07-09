# apps/app_standards/selectors/app_standards_selectors.py
"""
Read-only data fetching layer for App Standards domain.
Follows vendor pattern with sync and async dual methods.
Works with existing unified models (UnifiedAIUsage, UnifiedBillingIntegration, etc.).
"""

import asyncio
from typing import Optional, List
from apps.app_standards.models.unified_models import (
    UnifiedAIUsage,
    UnifiedBillingIntegration,
    UnifiedNotification,
    UnifiedRateLimit,
    UnifiedAccessPermission,
)


# ============================================================================
# SYNC SELECTORS (for DRF)
# ============================================================================

def get_ai_usage(user_id: str, service_type: str = None) -> List[UnifiedAIUsage]:
    """Get AI usage records for a user (sync)."""
    queryset = UnifiedAIUsage.objects.filter(user_id=user_id)
    if service_type:
        queryset = queryset.filter(service_type=service_type)
    return list(queryset.order_by('-created_at')[:20])


def get_billing_transactions(user_id: str, transaction_type: str = None) -> List[UnifiedBillingIntegration]:
    """Get billing transactions for a user (sync)."""
    queryset = UnifiedBillingIntegration.objects.filter(user_id=user_id)
    if transaction_type:
        queryset = queryset.filter(transaction_type=transaction_type)
    return list(queryset.order_by('-created_at')[:20])


def get_notifications(user_id: str, status: str = None) -> List[UnifiedNotification]:
    """Get notifications for a user (sync)."""
    queryset = UnifiedNotification.objects.filter(user_id=user_id)
    if status:
        queryset = queryset.filter(status=status)
    return list(queryset.order_by('-created_at')[:20])


def get_rate_limits(user_id: str, limit_type: str = None) -> List[UnifiedRateLimit]:
    """Get rate limits for a user (sync)."""
    queryset = UnifiedRateLimit.objects.filter(user_id=user_id)
    if limit_type:
        queryset = queryset.filter(limit_type=limit_type)
    return list(queryset.order_by('-created_at'))


def get_access_permissions(user_id: str, resource_type: str = None) -> List[UnifiedAccessPermission]:
    """Get access permissions for a user (sync)."""
    queryset = UnifiedAccessPermission.objects.filter(user_id=user_id)
    if resource_type:
        queryset = queryset.filter(resource_type=resource_type)
    return list(queryset.order_by('-created_at'))


def get_ai_usage_by_model(model_name: str, limit: int = 10) -> List[UnifiedAIUsage]:
    """Get AI usage by model name (sync)."""
    return list(
        UnifiedAIUsage.objects.filter(model_name=model_name)
        .order_by('-created_at')[:limit]
    )


# ============================================================================
# ASYNC SELECTORS (for Django Ninja)
# ============================================================================

async def aget_ai_usage(user_id: str, service_type: str = None) -> List[UnifiedAIUsage]:
    """Get AI usage records for a user (async)."""
    queryset = UnifiedAIUsage.objects.filter(user_id=user_id)
    if service_type:
        queryset = queryset.filter(service_type=service_type)
    return [u async for u in queryset.order_by('-created_at')[:20]]


async def aget_billing_transactions(user_id: str, transaction_type: str = None) -> List[UnifiedBillingIntegration]:
    """Get billing transactions for a user (async)."""
    queryset = UnifiedBillingIntegration.objects.filter(user_id=user_id)
    if transaction_type:
        queryset = queryset.filter(transaction_type=transaction_type)
    return [t async for t in queryset.order_by('-created_at')[:20]]


async def aget_notifications(user_id: str, status: str = None) -> List[UnifiedNotification]:
    """Get notifications for a user (async)."""
    queryset = UnifiedNotification.objects.filter(user_id=user_id)
    if status:
        queryset = queryset.filter(status=status)
    return [n async for n in queryset.order_by('-created_at')[:20]]


async def aget_rate_limits(user_id: str, limit_type: str = None) -> List[UnifiedRateLimit]:
    """Get rate limits for a user (async)."""
    queryset = UnifiedRateLimit.objects.filter(user_id=user_id)
    if limit_type:
        queryset = queryset.filter(limit_type=limit_type)
    return [r async for r in queryset.order_by('-created_at')]


async def aget_access_permissions(user_id: str, resource_type: str = None) -> List[UnifiedAccessPermission]:
    """Get access permissions for a user (async)."""
    queryset = UnifiedAccessPermission.objects.filter(user_id=user_id)
    if resource_type:
        queryset = queryset.filter(resource_type=resource_type)
    return [p async for p in queryset.order_by('-created_at')]


async def aget_ai_usage_by_model(model_name: str, limit: int = 10) -> List[UnifiedAIUsage]:
    """Get AI usage by model name (async)."""
    queryset = UnifiedAIUsage.objects.filter(model_name=model_name).order_by('-created_at')
    return [u async for u in queryset[:limit]]


# ============================================================================
# PARALLEL LOADING (async only)
# ============================================================================

async def aget_user_dashboard_parallel(user_id: str) -> dict:
    """
    Load user dashboard data in parallel using asyncio.gather.
    Returns AI usage, billing transactions, notifications, and rate limits.
    """
    ai_usage, billing, notifications, rate_limits = await asyncio.gather(
        aget_ai_usage(user_id),
        aget_billing_transactions(user_id),
        aget_notifications(user_id),
        aget_rate_limits(user_id),
        return_exceptions=True,
    )
    
    return {
        'ai_usage': ai_usage if not isinstance(ai_usage, Exception) else [],
        'billing_transactions': billing if not isinstance(billing, Exception) else [],
        'notifications': notifications if not isinstance(notifications, Exception) else [],
        'rate_limits': rate_limits if not isinstance(rate_limits, Exception) else [],
    }


async def aget_ai_usage_summary_parallel(user_id: str) -> dict:
    """
    Load AI usage summary in parallel using asyncio.gather.
    Returns total usage, cost, and recent records.
    """
    from django.db.models import Sum, Count
    
    queryset = UnifiedAIUsage.objects.filter(user_id=user_id)
    
    total_usage, total_cost, recent_records = await asyncio.gather(
        queryset.aggregate(Sum('input_tokens') + Sum('output_tokens')),
        queryset.aggregate(Sum('cost')),
        aget_ai_usage(user_id),
        return_exceptions=True,
    )
    
    return {
        'total_tokens': total_usage if not isinstance(total_usage, Exception) else 0,
        'total_cost': total_cost if not isinstance(total_cost, Exception) else 0,
        'recent_records': recent_records if not isinstance(recent_records, Exception) else [],
    }
