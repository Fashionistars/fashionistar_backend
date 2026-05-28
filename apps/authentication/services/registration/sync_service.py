import logging
from typing import Dict, Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from rest_framework import serializers as drf_serializers

from apps.authentication.models import UnifiedUser
from apps.authentication.services.otp import OTPService
from apps.common.events import event_bus  # EventBus singleton
from apps.audit_logs.services.authentication import auth_audit

# Configure logger for application-level events
logger = logging.getLogger(__name__)


class RegistrationService:
    """
    Centralised Registration Service.

    Orchestrates the full user registration pipeline, ensuring atomic database
    operations, OTP generation, and asynchronous notification dispatch.
    """

    @staticmethod
    def register_sync(
        email: str = None,
        phone: str = None,
        password: str = None,
        role: str = "client",
        request: Any = None,
        **extra_fields,
    ) -> Dict[str, Any]:
        """
        Synchronous User Registration.

        Completes database operations and schedules background tasks for OTP delivery
        and lifecycle registry. Ensures forensic audit logging for all outcomes.

        Args:
            email (str, optional): User email address.
            phone (str, optional): User phone in E.164 format.
            password (str, optional): Plain-text password to be hashed.
            role (str, optional): User role ('vendor', 'client'). Defaults to 'client'.
            request (HttpRequest, optional): Context for metadata capture (IP/UA).
            **extra_fields: Additional fields for the UnifiedUser model.

        Returns:
            Dict[str, Any]: Payload containing success message and user identifiers.

        Raises:
            serializers.ValidationError: On data integrity or validation failures.
        """
        # ── Lazily import Celery tasks to avoid circular dependencies ────────
        from apps.authentication.tasks import send_email_task, send_sms_task

        # ── Data Normalization ─────────────────────────────────────────────
        email = email or None
        phone = str(phone) if phone else None

        try:
            with transaction.atomic():
                # ── Strip validation-only fields ────────────────────────────
                for key in ("password_confirm", "password2", "password_confirmation"):
                    extra_fields.pop(key, None)

                # ── Default Auth Provider ──────────────────────────────────
                if email:
                    extra_fields.setdefault("auth_provider", "email")
                elif phone:
                    extra_fields.setdefault("auth_provider", "phone")

                # ── 1. Create User Row ─────────────────────────────────────
                try:
                    user = UnifiedUser.objects.create_user(
                        email=email,
                        phone=phone,
                        password=password,
                        role=role,
                        is_active=False,
                        is_verified=False,
                        **extra_fields,
                    )
                except DjangoValidationError as exc:
                    if hasattr(exc, "message_dict"):
                        raise drf_serializers.ValidationError(exc.message_dict)
                    raise drf_serializers.ValidationError({"error": exc.messages})
                except IntegrityError as exc:
                    err_str = str(exc).lower()
                    if "email" in err_str:
                        raise drf_serializers.ValidationError(
                            {"email": ["A user with this email address already exists."]}
                        )
                    if "phone" in err_str:
                        raise drf_serializers.ValidationError(
                            {"phone": ["A user with this phone number already exists."]}
                        )
                    raise drf_serializers.ValidationError(
                        {"error": ["A user with these details already exists."]}
                    )

                logger.info("✅ Registration: user created [id=%s]", user.id)

                # ── 2. Generate Verification OTP ────────────────────────────
                # PRIMARY: OTP stored in Redis with 5-minute TTL.
                # FALLBACK: If Redis is unavailable (Cloud Run cold-start, etc.),
                # we generate the OTP but store it in the Django DB cache table.
                # The admin can manually activate users, or the user can resend
                # OTP once Redis is restored. Registration MUST NOT fail due to
                # Redis unavailability — user creation is the atomic unit.
                otp = None
                try:
                    otp = OTPService.generate_otp_sync(
                        user.id, purpose="verify", request=request
                    )
                except Exception as otp_exc:
                    # Redis is unavailable — store OTP in Django's DB cache as fallback.
                    # This allows registration to succeed even without Redis.
                    logger.warning(
                        "⚠️ Registration: Redis unavailable for OTP, using DB cache fallback "
                        "[user_id=%s]: %s",
                        user.id,
                        str(otp_exc),
                    )
                    try:
                        from apps.common.utils import generate_numeric_otp
                        from django.core.cache import cache as _django_cache

                        otp = generate_numeric_otp()
                        # Store in Django DB cache with 10-minute TTL (600s)
                        _cache_key = f"otp_fallback:{user.id}:verify"
                        _django_cache.set(_cache_key, otp, timeout=600)
                        logger.info(
                            "✅ Registration: DB-cache OTP stored [user_id=%s key=%s]",
                            user.id,
                            _cache_key,
                        )
                    except Exception as fallback_exc:
                        # If even DB cache fails, log but DO NOT fail registration.
                        # Admin can manually activate this user.
                        logger.error(
                            "❌ Registration: OTP fallback also failed [user_id=%s]: %s. "
                            "User created but requires admin activation.",
                            user.id,
                            str(fallback_exc),
                        )
                        otp = None  # Registration continues, admin activates manually

                # ── 3. Wallet Provisioning (get_or_create) ─────────────────
                # ARCHITECTURAL REQUIREMENT: Every user on the Fashionistar
                # platform — whether CLIENT, VENDOR, ADMIN, SUPPORT, EDITOR,
                # SALES, or MODERATOR — MUST have their own wallet created at
                # registration time. This is a HARD platform invariant.
                #
                # PLATFORM VISION: Fashionistar is the central hub for all
                # financial transactions and payments. Staff members (support,
                # sales, editors, moderators) will be compensated directly from
                # their wallet dashboards via commission profits earned on the
                # platform. At the end of every month or on task/assignment
                # completion, their wallet balance will be credited or debited
                # and they will be notified accordingly.
                # (Full staff salary/commission payment system ships in V2 when
                # we build the Support and Admin fullstack micro-service apps.)
                #
                # INTEGRITY GUARANTEE: This provisioning is INSIDE the atomic
                # block so that if user creation OR wallet provisioning fails,
                # EVERYTHING rolls back cleanly via ACID transaction semantics.
                # This prevents orphaned users without wallets and orphaned
                # wallets without users — a critical financial data-integrity
                # requirement for CBN/PCI-DSS compliance.
                try:
                    from apps.wallet.services import WalletProvisioningService  # noqa: PLC0415
                    WalletProvisioningService.ensure_wallet(
                        user, currency_code="NGN", request=request
                    )
                    logger.info(
                        "✅ Registration: NGN wallet provisioned "
                        "[user_id=%s, role=%s]",
                        user.id,
                        user.role,
                    )
                except Exception as wallet_exc:
                    # Re-raise so the atomic transaction rolls back completely.
                    # A user without a wallet violates the financial architecture
                    # contract and MUST be treated as a registration failure.
                    logger.error(
                        "❌ Registration: wallet provisioning failed "
                        "[user_id=%s]: %s",
                        user.id,
                        str(wallet_exc),
                        exc_info=True,
                    )
                    raise


            # ── 4. Lifecycle & Audit Dispatch ──────────────────────────────
            # We use transaction.on_commit to ensure actions only fire if DB save succeeds.

            # Dispatch 'user.registered' event for downstream listeners
            event_bus.emit_on_commit(
                "user.registered",
                user_uuid=str(user.id),
                email=str(user.email) if user.email else None,
                phone=str(user.phone) if user.phone else None,
                member_id=str(user.member_id) if user.member_id else "",
                role=str(user.role) if user.role else "",
                auth_provider=str(user.auth_provider) if user.auth_provider else "email",
                country=str(user.country) if user.country else None,
                state=str(user.state) if user.state else None,
                city=str(user.city) if user.city else None,
            )

            # Record forensic audit trail
            transaction.on_commit(
                lambda: auth_audit.log_register_success(actor=user, request=request)
            )

            # ── 4. OTP Notification Dispatch ───────────────────────────────
            # RESILIENCE: Email/SMS tasks are dispatched via Celery (Redis broker).
            # If Celery/Redis is unavailable, we log the failure but DO NOT crash
            # the registration. The user is created and the admin can activate them.
            _user_id = str(user.id)
            _otp = otp
            _notification_sent = False

            from apps.audit_logs.middleware import extract_client_context
            _audit_ctx_dict = extract_client_context(request)

            if _otp and email:
                from django.conf import settings as _settings

                _email_context = {
                    "user_id": _user_id,
                    "otp": _otp,
                    "user_name": (
                        getattr(user, "first_name", None) or email.split("@")[0]
                    ),
                    "support_email": "support@fashionistar.io",
                    "SITE_URL": getattr(_settings, "SITE_URL", "https://fashionistar.io"),
                }
                try:
                    transaction.on_commit(
                        lambda: send_email_task.apply_async(
                            kwargs={
                                "subject": "🔐 Verify Your Fashionistar Account",
                                "recipients": [email],
                                "template_name": "authentication/email/registration_email.html",
                                "context": _email_context,
                                "audit_client_context": _audit_ctx_dict,
                            }
                        )
                    )
                    _notification_sent = True
                except Exception as email_exc:
                    logger.warning(
                        "⚠️ Registration: email dispatch failed [user_id=%s]: %s",
                        _user_id, str(email_exc),
                    )

            elif _otp and phone:
                _phone_body = (
                    "Welcome to Fashionistar!\n"
                    f"Your verification OTP is: {_otp}\n"
                    "Valid for 10 minutes. Do not share this code."
                )
                try:
                    transaction.on_commit(
                        lambda: send_sms_task.apply_async(
                            kwargs={
                                "to": phone,
                                "body": _phone_body,
                                "audit_client_context": _audit_ctx_dict,
                            }
                        )
                    )
                    _notification_sent = True
                except Exception as sms_exc:
                    logger.warning(
                        "⚠️ Registration: SMS dispatch failed [user_id=%s]: %s",
                        _user_id, str(sms_exc),
                    )

            # Determine appropriate success message based on notification state
            if _otp and _notification_sent:
                _success_message = (
                    "Registration successful. "
                    "Check your email or phone for your OTP verification code."
                )
            elif _otp:
                _success_message = (
                    "Registration successful. "
                    "Your account is pending verification. "
                    "Please contact support or check your email shortly."
                )
            else:
                _success_message = (
                    "Registration successful. "
                    "Your account has been created and is pending admin activation. "
                    "You will be notified once your account is activated."
                )

            return {
                "message": _success_message,
                "user_id": _user_id,
                "email": email,
                "phone": phone,
            }

        except Exception as exc:
            logger.error("❌ Registration failed: %s", str(exc), exc_info=True)

            # Best-effort audit: log the registration failure
            try:
                auth_audit.log_register_failed(
                    email=str(email or phone or "unknown"),
                    reason=str(exc)[:200],
                    request=request,
                )
            except Exception as audit_exc:
                logger.warning("⚠️ Registration audit failure log failed: %s", audit_exc)

            raise
