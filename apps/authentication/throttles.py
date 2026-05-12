# apps/authentication/throttles.py
"""
Advanced Throttling & Rate Limiting Framework for Authentication API.

This module implements a three-tier throttling strategy:
1. BurstRateThrottle: Strict limits for anonymous/sensitive endpoints.
2. SustainedRateThrottle: Standard limits for authenticated users.
3. RoleBasedAdaptiveThrottle: Dynamic scaling based on user role.

All throttle violations are:
  - Logged to the Django logger (existing)
  - Written to AuditEventLog as LOGIN_BLOCKED / SECURITY events (NEW)
  - Recorded as LoginEvent with outcome=BLOCKED (NEW, where applicable)
"""

import logging
from typing import Optional
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

logger = logging.getLogger('application')


# ════════════════════════════════════════════════════════════════════════════
# Helper: fire audit event for throttle violation (non-blocking, never raises)
# ════════════════════════════════════════════════════════════════════════════

def _audit_throttle_violation(
    request,
    scope: str,
    wait_time,
    endpoint_hint: str = "",
) -> None:
    """
    Write a throttle violation to AuditEventLog.

    Called from throttle_failure() in every throttle class.
    Guaranteed never to raise — all errors swallowed.

    Args:
        request:       The DRF request object.
        scope:         Throttle scope string (e.g. 'auth_burst').
        wait_time:     Seconds until the client may retry.
        endpoint_hint: URL path string (from request.path or passed in).
    """
    try:
        from apps.audit_logs.services.audit import AuditService
        from apps.audit_logs.models import EventType, EventCategory, SeverityLevel

        ip_address = None
        user_agent = None
        request_path = endpoint_hint
        actor = None
        actor_email = None

        if request:
            xff = getattr(request, 'META', {}).get('HTTP_X_FORWARDED_FOR', '')
            ip_address = xff.split(',')[0].strip() if xff else getattr(
                request, 'META', {}
            ).get('REMOTE_ADDR', '0.0.0.0')
            user_agent = getattr(request, 'META', {}).get('HTTP_USER_AGENT', '')
            request_path = request_path or getattr(request, 'path', '')
            drf_user = getattr(request, 'user', None)
            if drf_user and getattr(drf_user, 'is_authenticated', False):
                actor = drf_user
                actor_email = getattr(drf_user, 'email', None)

        AuditService.log(
            event_type=EventType.LOGIN_BLOCKED,
            event_category=EventCategory.SECURITY,
            severity=SeverityLevel.WARNING,
            action=(
                f"Rate limit exceeded — scope={scope} | "
                f"endpoint={request_path} | retry_in={wait_time}s"
            ),
            request=request,
            actor=actor,
            actor_email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
            response_status=429,
            metadata={
                "throttle_scope": scope,
                "retry_after_seconds": wait_time,
                "endpoint": request_path,
            },
            error_message=f"Throttle scope '{scope}' exceeded",
            is_compliance=True,
        )
    except Exception:
        # Never block the HTTP response path — this is purely informational
        pass


def _record_throttle_login_event(request, scope: str) -> None:
    """
    Record a LoginEvent with outcome=BLOCKED for throttle violations on
    auth/login and password-reset endpoints.

    Only fires for endpoints that look like login or password-reset.
    Non-auth endpoints skip this (to avoid noise in the security dashboard).
    """
    try:
        path = getattr(request, 'path', '') or ''
        is_auth_endpoint = any(
            p in path for p in (
                '/login', '/password', '/reset', '/otp', '/verify',
                '/register', '/token',
            )
        )
        if not is_auth_endpoint:
            return

        from apps.authentication.models import LoginEvent

        xff = getattr(request, 'META', {}).get('HTTP_X_FORWARDED_FOR', '')
        ip = xff.split(',')[0].strip() if xff else getattr(
            request, 'META', {}
        ).get('REMOTE_ADDR', '0.0.0.0')
        ua = getattr(request, 'META', {}).get('HTTP_USER_AGENT', '')

        # Resolve user (may be anonymous on throttled endpoints)
        drf_user = getattr(request, 'user', None)
        user = drf_user if (drf_user and getattr(drf_user, 'is_authenticated', False)) else None

        LoginEvent.record(
            user=user,
            ip_address=ip or '0.0.0.0',
            user_agent=ua,
            auth_method=LoginEvent.METHOD_EMAIL,
            outcome=LoginEvent.OUTCOME_BLOCKED,
            failure_reason=f'rate_limited:{scope}',
            is_successful=False,
        )
    except Exception:
        pass


# ============================================================================
# TIER 1: BURST RATE THROTTLE (Sensitive Endpoints)
# ============================================================================

class BurstRateThrottle(AnonRateThrottle):
    """
    Strict Rate Limiting for Sensitive Operations.
    Limit: 10 requests per minute per IP.

    Throttle violations → AuditEventLog + LoginEvent (for auth paths).
    """
    scope = 'auth_burst'
    rate = '10/min'

    def throttle_success(self):
        result = super().throttle_success()
        return result

    def throttle_failure(self):
        try:
            wait_time = self.wait() if hasattr(self, 'wait') and callable(self.wait) else 60
            ip_address = self.get_ident(self.request) if hasattr(self, 'request') else 'UNKNOWN'
            path = getattr(self.request, 'path', 'UNKNOWN') if hasattr(self, 'request') else 'UNKNOWN'

            logger.warning(
                "⛔ BURST THROTTLE TRIGGERED | Scope: %s | IP: %s | "
                "Retry-After: %ss | Endpoint: %s",
                self.scope, ip_address, wait_time, path,
            )

            req = getattr(self, 'request', None)
            # Write to AuditEventLog
            _audit_throttle_violation(req, self.scope, wait_time, path)
            # Write to LoginEvent (for auth-related endpoints only)
            if req:
                _record_throttle_login_event(req, self.scope)

        except Exception as e:
            logger.error("Error in BurstRateThrottle.throttle_failure: %s", e)

        return super().throttle_failure()

    def allow_request(self, request, view) -> bool:
        try:
            self.request = request
            return super().allow_request(request, view)
        except Exception as e:
            logger.error("Error in BurstRateThrottle.allow_request: %s", e)
            return True


# ============================================================================
# TIER 2: SUSTAINED RATE THROTTLE (Standard Users)
# ============================================================================

class SustainedRateThrottle(UserRateThrottle):
    """
    Standard Rate Limiting for Authenticated Users.
    Limit: 1000 requests per day.

    Sustained violations are written to AuditEventLog (lower severity — INFO).
    """
    scope = 'auth_sustained'
    rate = '1000/day'

    def get_rate(self) -> Optional[str]:
        return self.rate

    def throttle_failure(self):
        try:
            wait_time = self.wait() if hasattr(self, 'wait') and callable(self.wait) else 86400
            req = getattr(self, 'request', None)
            path = getattr(req, 'path', 'UNKNOWN') if req else 'UNKNOWN'

            logger.warning(
                "⛔ SUSTAINED THROTTLE TRIGGERED | Scope: %s | Retry-After: %ss | Endpoint: %s",
                self.scope, wait_time, path,
            )
            _audit_throttle_violation(req, self.scope, wait_time, path)
        except Exception as e:
            logger.error("Error in SustainedRateThrottle.throttle_failure: %s", e)
        return super().throttle_failure()

    def allow_request(self, request, view) -> bool:
        try:
            self.request = request
            return super().allow_request(request, view)
        except Exception as e:
            logger.error("Error in SustainedRateThrottle.allow_request: %s", e)
            return True


# ============================================================================
# TIER 3: ROLE-BASED ADAPTIVE THROTTLE (Dynamic Scaling)
# ============================================================================

class RoleBasedAdaptiveThrottle(UserRateThrottle):
    """
    Dynamic Throttling Based on User Role (RBAC Integration).

    Violations written to AuditEventLog with role context.
    """
    scope = 'auth_adaptive'

    def get_rate(self) -> str:
        try:
            user = self.request.user if hasattr(self, 'request') else None

            if not user or not user.is_authenticated:
                return '100/day'

            role = getattr(user, 'role', 'client').lower()

            if role in ['admin', 'superuser', 'staff']:
                limit = '100000/day'
            elif role == 'vendor':
                limit = '10000/day'
            else:
                limit = '2000/day'

            return limit

        except Exception as e:
            logger.warning("Error determining adaptive throttle rate: %s | Defaulting to 1000/day", e)
            return '1000/day'

    def throttle_failure(self):
        try:
            wait_time = self.wait() if hasattr(self, 'wait') and callable(self.wait) else 86400
            req = getattr(self, 'request', None)
            path = getattr(req, 'path', 'UNKNOWN') if req else 'UNKNOWN'

            logger.warning(
                "⛔ ADAPTIVE THROTTLE TRIGGERED | Scope: %s | Role: %s | Retry-After: %ss | Endpoint: %s",
                self.scope,
                getattr(getattr(req, 'user', None), 'role', 'unknown') if req else 'unknown',
                wait_time,
                path,
            )
            _audit_throttle_violation(req, self.scope, wait_time, path)
        except Exception as e:
            logger.error("Error in RoleBasedAdaptiveThrottle.throttle_failure: %s", e)
        return super().throttle_failure()

    def allow_request(self, request, view) -> bool:
        try:
            self.request = request
            self.rate = self.get_rate()
            self.num_requests, self.duration = self.parse_rate(self.rate)
            return super().allow_request(request, view)
        except Exception as e:
            logger.error("Error in RoleBasedAdaptiveThrottle.allow_request: %s", e)
            return True
