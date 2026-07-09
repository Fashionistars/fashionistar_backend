# apps/app_standards/views/async_views.py
"""
Django Ninja async views for App Standards domain.
Follows vendor pattern with async endpoints under /api/v1/ninja/app-standards/.
"""

# pyrefly: ignore [missing-import]
from ninja import Router
# pyrefly: ignore [missing-import]
from django.http import HttpRequest
from typing import List, Optional
from pydantic import BaseModel
from apps.app_standards.selectors.app_standards_selectors import (
    aget_ai_usage,
    aget_billing_transactions,
    aget_notifications,
    aget_rate_limits,
    aget_user_dashboard_parallel,
    aget_ai_usage_summary_parallel,
)
from apps.app_standards.models.unified_models import UnifiedAIUsage, UnifiedBillingIntegration


router = Router(tags=['App Standards'])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class AIUsageResponse(BaseModel):
    usage_id: str
    service_type: str
    model_name: str
    input_tokens: int
    output_tokens: int
    processing_time: float
    cost: str
    success: bool
    created_at: str


class BillingTransactionResponse(BaseModel):
    transaction_id: str
    transaction_type: str
    amount: str
    gateway: str
    reference_id: str
    status: str
    created_at: str


class NotificationResponse(BaseModel):
    notification_id: str
    notification_type: str
    title: str
    content: str
    priority: str
    status: str
    created_at: str


class RateLimitResponse(BaseModel):
    limit_id: str
    endpoint: str
    limit_type: str
    max_requests: int
    current_count: int
    window_start: str


class UserDashboardResponse(BaseModel):
    ai_usage: List[AIUsageResponse]
    billing_transactions: List[BillingTransactionResponse]
    notifications: List[NotificationResponse]
    rate_limits: List[RateLimitResponse]


class AIUsageSummaryResponse(BaseModel):
    total_tokens: int
    total_cost: str
    recent_records: List[AIUsageResponse]


# ============================================================================
# Async Endpoints
# ============================================================================

@router.get('/ai-usage/', response=List[AIUsageResponse])
async def get_ai_usage(request: HttpRequest, service_type: Optional[str] = None):
    """
    Get AI usage records for authenticated user (async).
    Endpoint: GET /api/v1/ninja/app-standards/ai-usage/
    """
    user = request.auth
    if not user:
        return []
    
    usage_records = await aget_ai_usage(str(user.id), service_type)
    
    return [
        AIUsageResponse(
            usage_id=str(u.id),
            service_type=u.service_type,
            model_name=u.model_name,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            processing_time=u.processing_time,
            cost=str(u.cost),
            success=u.success,
            created_at=u.created_at.isoformat(),
        )
        for u in usage_records
    ]


@router.get('/billing/', response=List[BillingTransactionResponse])
async def get_billing_transactions(request: HttpRequest, transaction_type: Optional[str] = None):
    """
    Get billing transactions for authenticated user (async).
    Endpoint: GET /api/v1/ninja/app-standards/billing/
    """
    user = request.auth
    if not user:
        return []
    
    transactions = await aget_billing_transactions(str(user.id), transaction_type)
    
    return [
        BillingTransactionResponse(
            transaction_id=str(t.id),
            transaction_type=t.transaction_type,
            amount=str(t.amount),
            gateway=t.gateway,
            reference_id=t.reference_id,
            status=t.status,
            created_at=t.created_at.isoformat(),
        )
        for t in transactions
    ]


@router.get('/notifications/', response=List[NotificationResponse])
async def get_notifications(request: HttpRequest, status: Optional[str] = None):
    """
    Get notifications for authenticated user (async).
    Endpoint: GET /api/v1/ninja/app-standards/notifications/
    """
    user = request.auth
    if not user:
        return []
    
    notifications = await aget_notifications(str(user.id), status)
    
    return [
        NotificationResponse(
            notification_id=str(n.id),
            notification_type=n.notification_type,
            title=n.title,
            content=n.content,
            priority=n.priority,
            status=n.status,
            created_at=n.created_at.isoformat(),
        )
        for n in notifications
    ]


@router.get('/rate-limits/', response=List[RateLimitResponse])
async def get_rate_limits(request: HttpRequest, limit_type: Optional[str] = None):
    """
    Get rate limits for authenticated user (async).
    Endpoint: GET /api/v1/ninja/app-standards/rate-limits/
    """
    user = request.auth
    if not user:
        return []
    
    rate_limits = await aget_rate_limits(str(user.id), limit_type)
    
    return [
        RateLimitResponse(
            limit_id=str(r.id),
            endpoint=r.endpoint,
            limit_type=r.limit_type,
            max_requests=r.max_requests,
            current_count=r.current_count,
            window_start=r.window_start.isoformat(),
        )
        for r in rate_limits
    ]


@router.get('/dashboard/', response=UserDashboardResponse)
async def get_user_dashboard(request: HttpRequest):
    """
    Get user dashboard data in parallel (async).
    Endpoint: GET /api/v1/ninja/app-standards/dashboard/
    """
    user = request.auth
    if not user:
        return UserDashboardResponse(ai_usage=[], billing_transactions=[], notifications=[], rate_limits=[])
    
    dashboard_data = await aget_user_dashboard_parallel(str(user.id))
    
    return UserDashboardResponse(
        ai_usage=[
            AIUsageResponse(
                usage_id=str(u.id),
                service_type=u.service_type,
                model_name=u.model_name,
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                processing_time=u.processing_time,
                cost=str(u.cost),
                success=u.success,
                created_at=u.created_at.isoformat(),
            )
            for u in dashboard_data['ai_usage']
        ],
        billing_transactions=[
            BillingTransactionResponse(
                transaction_id=str(t.id),
                transaction_type=t.transaction_type,
                amount=str(t.amount),
                gateway=t.gateway,
                reference_id=t.reference_id,
                status=t.status,
                created_at=t.created_at.isoformat(),
            )
            for t in dashboard_data['billing_transactions']
        ],
        notifications=[
            NotificationResponse(
                notification_id=str(n.id),
                notification_type=n.notification_type,
                title=n.title,
                content=n.content,
                priority=n.priority,
                status=n.status,
                created_at=n.created_at.isoformat(),
            )
            for n in dashboard_data['notifications']
        ],
        rate_limits=[
            RateLimitResponse(
                limit_id=str(r.id),
                endpoint=r.endpoint,
                limit_type=r.limit_type,
                max_requests=r.max_requests,
                current_count=r.current_count,
                window_start=r.window_start.isoformat(),
            )
            for r in dashboard_data['rate_limits']
        ],
    )


@router.get('/ai-usage-summary/', response=AIUsageSummaryResponse)
async def get_ai_usage_summary(request: HttpRequest):
    """
    Get AI usage summary in parallel (async).
    Endpoint: GET /api/v1/ninja/app-standards/ai-usage-summary/
    """
    user = request.auth
    if not user:
        return AIUsageSummaryResponse(total_tokens=0, total_cost='0.0000', recent_records=[])
    
    summary_data = await aget_ai_usage_summary_parallel(str(user.id))
    
    return AIUsageSummaryResponse(
        total_tokens=summary_data['total_tokens'] or 0,
        total_cost=str(summary_data['total_cost'] or 0),
        recent_records=[
            AIUsageResponse(
                usage_id=str(u.id),
                service_type=u.service_type,
                model_name=u.model_name,
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                processing_time=u.processing_time,
                cost=str(u.cost),
                success=u.success,
                created_at=u.created_at.isoformat(),
            )
            for u in summary_data['recent_records']
        ],
    )


@router.post('/ai-usage/')
async def create_ai_usage(request: HttpRequest, service_type: str, model_name: str, input_tokens: int, output_tokens: int, processing_time: float):
    """
    Create AI usage record (async).
    Endpoint: POST /api/v1/ninja/app-standards/ai-usage/
    """
    from apps.app_standards.models.unified_models import UnifiedAIUsage
    from apps.audit_logs.services.app_standards import AppStandardsAuditService
    from decimal import Decimal
    
    user = request.auth
    if not user:
        return {'error': 'Authentication required'}
    
    # Create usage record
    usage = await UnifiedAIUsage.objects.acreate(
        user=user,
        service_type=service_type,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        processing_time=processing_time,
        cost=Decimal('0.0000'),
        success=True,
    )
    
    # Log audit event
    AppStandardsAuditService.log_ai_usage(
        actor=user,
        usage_id=str(usage.id),
        service_type=service_type,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=str(usage.cost),
        request=request,
    )
    
    return {
        'usage_id': str(usage.id),
        'message': 'AI usage recorded successfully',
    }
