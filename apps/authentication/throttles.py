# apps/authentication/throttles.py
"""
Advanced Throttling & Rate Limiting Framework for Authentication API.

This module implements a three-tier throttling strategy:
1. BurstRateThrottle: Strict limits for anonymous/sensitive endpoints.
2. SustainedRateThrottle: Standard limits for authenticated users.
3. RoleBasedAdaptiveThrottle: Dynamic scaling based on user role.
"""

import logging
from typing import Tuple, Optional
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.exceptions import Throttled
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger('application')


# ============================================================================
# TIER 1: BURST RATE THROTTLE (Sensitive Endpoints)
# ============================================================================

class BurstRateThrottle(AnonRateThrottle):
    """
    Strict Rate Limiting for Sensitive Operations.
    Limit: 10 requests per minute per IP.
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
            
            logger.warning(
                f"⛔ BURST THROTTLE TRIGGERED | Scope: {self.scope} | IP: {ip_address} | "
                f"Retry-After: {wait_time}s | Endpoint: {getattr(self.request, 'path', 'UNKNOWN')}"
            )
        except Exception as e:
            logger.error(f"Error in throttle_failure logging: {str(e)}")

        return super().throttle_failure()

    def allow_request(self, request, view) -> bool:
        try:
            self.request = request
            return super().allow_request(request, view)
        except Exception as e:
            logger.error(f"Error in BurstRateThrottle.allow_request: {str(e)}")
            return True


# ============================================================================
# TIER 2: SUSTAINED RATE THROTTLE (Standard Users)
# ============================================================================

class SustainedRateThrottle(UserRateThrottle):
    """
    Standard Rate Limiting for Authenticated Users.
    Limit: 1000 requests per day.
    """
    scope = 'auth_sustained'
    rate = '1000/day'

    def get_rate(self) -> Optional[str]:
        return self.rate

    def allow_request(self, request, view) -> bool:
        try:
            self.request = request
            return super().allow_request(request, view)
        except Exception as e:
            logger.error(f"Error in SustainedRateThrottle.allow_request: {str(e)}")
            return True


# ============================================================================
# TIER 3: ROLE-BASED ADAPTIVE THROTTLE (Dynamic Scaling)
# ============================================================================

class RoleBasedAdaptiveThrottle(UserRateThrottle):
    """
    Dynamic Throttling Based on User Role (RBAC Integration).
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
            logger.warning(f"Error determining adaptive throttle rate: {str(e)} | Defaulting to 1000/day")
            return '1000/day'

    def allow_request(self, request, view) -> bool:
        try:
            self.request = request
            self.rate = self.get_rate()
            self.num_requests, self.duration = self.parse_rate(self.rate)
            return super().allow_request(request, view)
        except Exception as e:
            logger.error(f"Error in RoleBasedAdaptiveThrottle.allow_request: {str(e)}")
            return True
