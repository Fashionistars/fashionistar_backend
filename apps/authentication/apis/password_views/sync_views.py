# apps/authentication/apis/password_views/sync_views.py
"""
Synchronous Password Management Views — Enterprise Production Edition.
=====================================================================
This module provides the API endpoints for secure password lifecycle management, 
including reset requests, token-based confirmation, and authenticated password changes.

Architecture:
    - Business logic is delegated to the `SyncPasswordService`.
    - Views handle request orchestration, serialization, and response normalization.
    - Audit logging is integrated via `AuditService` (SIEM-ready).
    - Asynchronous notifications (Email/SMS) are handled via Celery.

Security Measures:
    - Generic success responses to prevent user enumeration.
    - Strict rate limiting on public endpoints.
    - Transactional atomicity for all data mutations.
    - Required verification for sensitive account changes.

Endpoints covered:
  POST /api/v1/password/reset-request/
      → initiate email or phone-based reset (anonymous, rate-limited)

  POST /api/v1/password/reset-confirm/<uidb64>/<token>/
      → finalize email reset via link-token pair

  POST /api/v1/password/reset-phone-confirm/
      → finalize phone reset via OTP code

  POST /api/v1/password/change/
      → authenticated user changes own password from dashboard
        Permission: IsVerifiedUser  (active + OTP-verified)
        Decorator:  @require_verification  (inline double-check)

Security posture:
  - All public endpoints return the SAME generic success message regardless
    of whether the account exists (prevents user-enumeration).
  - Rate limiting applied via RateLimitPermission (100 req/hour per IP).
  - Password change wraps the save() in transaction.atomic() + on_commit
    for the notification email.
  - AuditService.log() called on every password event for SIEM compliance.
  - All actions are logged via the 'application' logger for SIEM ingestion.
 - SyncPasswordService owns business logic and audit behavior
  - views only translate service outcomes into stable API responses
"""

from __future__ import annotations

import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BrowsableAPIRenderer

from apps.authentication.serializers import (
    PasswordChangeSerializer,
    PasswordResetConfirmEmailSerializer,
    PasswordResetConfirmPhoneSerializer,
    PasswordResetRequestSerializer,
)
from apps.authentication.services.password_service import SyncPasswordService
from apps.common.permissions import (
    IsVerifiedUser,
    RateLimitPermission,
    require_verification,
)
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response

# Global application logger for SIEM and diagnostic tracing
logger = logging.getLogger("application")


def _frontend_url(path: str) -> str:
    """Constructs an absolute URL to the frontend application.

    Args:
        path (str): The relative path (e.g., '/auth/reset-password').

    Returns:
        str: The fully qualified URL including the protocol and origin.
    """
    # Defaults to localhost:3000 if FRONTEND_URL is missing from environment/settings
    origin = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    return f"{origin}{path}"


@extend_schema(tags=["Authentication"])
class PasswordResetRequestView(generics.GenericAPIView):
    """Initiates a password reset flow for either email or phone identifiers.

    This view handles the entry point of the "forgot password" journey. It 
    delegates the logic of generating tokens or OTPs to the service layer.

    Security:
        - Rate limited by IP to prevent automated account discovery attempts.
        - Always returns a 200 OK with a generic message to mask user existence.
    """
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny, RateLimitPermission]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_scope = "password_reset"

    def post(self, request, *args, **kwargs):
        """Processes the reset request and triggers background notification.

        Args:
            request (Request): The incoming DRF request object.

        Returns:
            Response: A standardized success response, regardless of account existence.
        """
        # Step 1: Validate input (Email or Phone format)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            # Step 2: Delegate to Service Layer
            # This handles user lookup, token/OTP generation, and Celery task dispatch.
            message = SyncPasswordService.request_reset(
                serializer.validated_data["email_or_phone"],
                request=request,
            )
        except Exception as exc:
            # Security: If a critical error occurs, log it for Sentry but 
            # still return the generic message to the client.
            logger.error(
                "CRITICAL: PasswordResetRequest unexpected error: %s", 
                exc, 
                exc_info=True,
                extra={"request_id": getattr(request, "request_id", None)}
            )
            message = "If an account exists, a reset code has been sent."

        # Finalize: Return success to maintain anti-enumeration posture
        return success_response(message=message, status=status.HTTP_200_OK)


@extend_schema(tags=["Authentication"])
class PasswordResetConfirmEmailView(generics.GenericAPIView):
    """Finalizes an email-based password reset using a cryptographically signed token.

    Validates the `uidb64` (User ID) and `token` parameters against the system's 
    security standards before updating the user's password.
    URL parameters uidb64 and token are validated against Django's
    default_token_generator.

    On success: audit event PASSWORD_RESET_COMPLETED (compliance=True)

    - POST /api/v1/password/reset-confirm/<uidb64>/<token>/ 
    """
    serializer_class = PasswordResetConfirmEmailSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, uidb64, token, *args, **kwargs):
        """Updates the user's password if the token and uidb64 are valid.

        Args:
            request (Request): The DRF request containing the new password.
            uidb64 (str): Base64 encoded user ID from the URL.
            token (str): One-time use token from the URL.

        Returns:
            Response: Success confirmation or a 400 Bad Request if validation fails.
        """
        # Step 1: Combine URL parameters with body data for serialization
        serializer = self.get_serializer(
            data={**request.data, "uidb64": uidb64, "token": token}
        )
        serializer.is_valid(raise_exception=True)

        try:
            # Step 2: Finalize reset via Service
            # This includes password hashing and audit logging.
            message = SyncPasswordService.confirm_reset(
                {
                    "uidb64": uidb64,
                    "token": token,
                    "new_password": serializer.validated_data["password"],
                },
                request=request,
            )
            return success_response(message=message, status=status.HTTP_200_OK)
        except Exception as exc:
            # Failure: Log warning and guide the user back to the start
            logger.warning("WARN: PasswordResetConfirmEmail validation failed: %s", exc)
            return error_response(
                message="The password reset link is invalid or has expired.",
                code="invalid_token",
                status=status.HTTP_400_BAD_REQUEST,
                errors={
                    "actions": {
                        "forgot_password_page": _frontend_url("/auth/forgot-password"),
                    }
                },
            )


@extend_schema(tags=["Authentication"])
class PasswordResetConfirmPhoneView(generics.GenericAPIView):
    """Finalizes a phone-based password reset using a 6-digit OTP code.

    Authenticates the reset attempt by verifying the OTP sent to the user's 
    registered mobile device.
    
    Body:
        otp       — 6-digit code sent via SMS
        password  — new password
        password2 — confirmation
        
    On success: audit event PASSWORD_RESET_COMPLETED (compliance=True)
    """
    serializer_class = PasswordResetConfirmPhoneSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs):
        """Verifies the OTP and updates the user's password.

        Args:
            request (Request): The DRF request containing OTP and new password.

        Returns:
            Response: Success confirmation or a 400 Bad Request if verification fails.
        """
        # Step 1: Validate request body
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            # Step 2: Verify OTP and reset password via Service
            message = SyncPasswordService.confirm_reset(
                {
                    "token": serializer.validated_data["otp"],
                    "new_password": serializer.validated_data["new_password"],
                },
                request=request,
            )
            return success_response(message=message, status=status.HTTP_200_OK)
        except Exception as exc:
            # Failure: Provide context for the frontend to handle retry/resend
            logger.warning("WARN: PasswordResetConfirmPhone verification failed: %s", exc)
            return error_response(
                message="The provided OTP is invalid or has expired.",
                code="invalid_otp",
                status=status.HTTP_400_BAD_REQUEST,
                errors={
                    "actions": {
                        "resend_otp": _frontend_url("/auth/forgot-password"),
                        "confirm_phone_page": _frontend_url(
                            "/auth/forgot-password/confirm-phone"
                        ),
                    }
                },
            )


@extend_schema(tags=["Authentication"])
class ChangePasswordView(generics.GenericAPIView):
    """Allows an authenticated, verified user to change their own password.

    This endpoint requires the strictest security posture:
        1. Authentication (JWT/Session).
        2. Account status (Active).
        3. Double-factor verification (require_verification decorator).
        4. POST /api/v1/password/change/   

    Body:
        old_password  — current password
        password      — new password
        password2     — confirmation

    Permission gate (strictest possible for account-mutating actions):
        IsVerifiedUser  — user must be authenticated, active, AND OTP-verified.

    Flow:
        1. Validate old password + new password (DRF serializer).
        2. transaction.atomic() — set new password and save().
        3. AuditService.log(PASSWORD_CHANGED) — compliance record.
        4. transaction.on_commit() — fire confirmation email via Celery.
    """
    serializer_class = PasswordChangeSerializer
    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @require_verification
    def post(self, request, *args, **kwargs):
        """Authenticates current password and updates to a new one.

        Args:
            request (Request): The DRF request with old and new passwords.

        Returns:
            Response: Success confirmation or detailed error.
        """
        # Step 1: Validation
        # The serializer checks password strength and basic equality constraints.
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            # Step 2: Atomic Update
            # Delegates to service for old_password verification and new_password hashing.
            # Side-effects (email notification) are queued via transaction.on_commit inside service.
            message = SyncPasswordService.change_password(
                user=request.user,
                old_password=serializer.validated_data["old_password"],
                new_password=serializer.validated_data["new_password"],
                request=request,
            )
            return success_response(message=message, status=status.HTTP_200_OK)
        except Exception as exc:
            # Step 3: Failure Handling
            # Distinct handling for password mismatch vs. system failures.
            logger.error(
                "ERROR: ChangePassword operation failed: %s", 
                exc, 
                exc_info=True,
                extra={"user_id": request.user.id}
            )
            detail = str(exc)
            
            if "current password is incorrect" in detail.lower():
                return error_response(
                    message="The current password you provided is incorrect.",
                    code="invalid_current_password",
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            return error_response(
                message="Unable to change password at this time. Please contact support.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )














