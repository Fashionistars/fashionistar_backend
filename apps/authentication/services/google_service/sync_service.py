# apps/authentication/services/google_service/sync_service.py
"""
Sync Google OAuth2 Service — Enterprise Edition
================================================

Handles the full Hybrid-Flow for Google Sign-In:

  1. Verify the Google ID-token with Google's public keys (blocking → uses
     the standard ``google-auth`` library — safe in WSGI).
  2. Extract rich profile data (email, first_name, last_name, full_name,
     google_avatar_url, locale).
  3. **Existing user** → straight login, return JWT tokens.
  4. **New user** → create via ``UnifiedUser.objects.create_user()``
     (generates member_id, hashes unusable password, sets is_verified=True).
  5. **Wallet Provisioning** → every new user gets an NGN wallet via
     WalletProvisioningService.ensure_wallet() — inside the atomic block so
     wallet failures roll back user creation atomically (no orphans).
  6. **Google avatar** → schedule a Celery task to download and re-upload
     the Google profile picture to Cloudinary (our Cloudinary CDN).
     The avatar URL is stored as the Cloudinary HTTPS secure_url after
     the webhook fires, so the user is never served a Google-controlled URL.
  7. **EventBus** → emit ``user.registered`` for new users so the welcome
     email, analytics increment, and any future subscribers are triggered
     in a fire-and-forget fashion via ``transaction.on_commit``.

Returns:
    dict with ``user`` (UnifiedUser instance) and ``tokens`` (access + refresh).

Bug Fixes (Wave B1):
    - Added ``from typing import Any`` — was missing, causing NameError at startup.
    - Fixed unreachable exception handler: ``except (ValueError, Exception): raise``
      made ``log_login_failed()`` permanently unreachable dead code.
    - Added WalletProvisioningService.ensure_wallet() for new Google users.
"""

import logging
from typing import Any

from django.conf import settings
from django.db import transaction

logger = logging.getLogger('application')


class SyncGoogleAuthService:
    """
    Synchronous Service for Google OAuth2 (Hybrid Flow).
    """

    @staticmethod
    def verify_and_login(
        token: str,
        role: str = 'client',
        *,
        request: Any = None,
    ) -> dict:
        """Verify Google ID-token, find-or-create user, and return JWT tokens.

        This service implements the Google OAuth2 Hybrid Flow backend verification.
        It validates the token against Google's public keys, extracts profile data,
        and either logs in an existing user or registers a new one.

        Args:
            token: The Google-provided ID token from the frontend.
            role: The role to assign if a new user is created ('client' or 'vendor').
            request: Optional Django HttpRequest for audit metadata (IP, UA).

        Returns:
            dict: {
                "user": UnifiedUser instance,
                "tokens": {"access": str, "refresh": str},
                "is_new": bool
            }

        Raises:
            ValueError: If the Google token is invalid or email is unverified.
            Exception: For unexpected infrastructure failures.
        """
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        from apps.authentication.models import UnifiedUser
        from rest_framework_simplejwt.tokens import RefreshToken
        from apps.audit_logs.services.authentication import auth_audit

        # Track email for failure audit (may be set in token verification phase)
        email: str = ''

        # ── 1. Token Verification ──────────────────────────────────────────
        try:
            # ── 1. Verify token with Google ────────────────────────────────
            id_info = google_id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )

            email = id_info.get('email') or ''
            if not email:
                raise ValueError("Email not found in Google Token.")

            if not id_info.get('email_verified', False):
                raise ValueError("Google email is not verified.")

            # Normalise email domain to lowercase only for email
            from django.contrib.auth.base_user import BaseUserManager as _BUM
            if email and "@" in email:
                email = _BUM.normalize_email(email)

            # ── 2. Extract rich profile data ───────────────────────────────
            first_name        = id_info.get('given_name', '')   or ''
            last_name         = id_info.get('family_name', '')  or ''
            google_avatar_url = id_info.get('picture', '')      or ''
            google_sub        = id_info.get('sub', '')           or ''

            logger.info(
                "🔍 Google token verified — email=%s sub=%s", email, google_sub
            )

        except ValueError as exc:
            logger.error("❌ Google token verification failed: %s", exc)
            raise ValueError("Invalid or expired Google Token.") from exc
        except Exception as exc:
            logger.error(
                "❌ Unexpected error during Google token verification: %s",
                exc, exc_info=True
            )
            raise Exception("Google authentication failed. Please try again.") from exc

        # ── 3. Find or Create User ─────────────────────────────────────────
        try:
            is_new = False
            user = None

            try:
                user = UnifiedUser.objects.get(email=email)
                logger.info("✅ Google Login: existing user %s", email)
            except UnifiedUser.DoesNotExist:
                # New user — create via create_user() to go through the full
                # manager pipeline: member_id generation, unusable password,
                # full_clean() validation.
                with transaction.atomic():
                    # Resolve geo-data for the new account
                    ip_address = None
                    if request:
                        # Extract IP if request object provided
                        from apps.audit_logs.services.audit import _get_client_ip  # noqa: PLC0415
                        ip_address = _get_client_ip(request)

                    geo_data: dict = {}
                    if ip_address:
                        try:
                            from apps.audit_logs.services.audit import _resolve_geo  # noqa: PLC0415
                            geo_data = _resolve_geo(ip_address) or {}
                        except Exception as geo_exc:
                            logger.warning("⚠️ Google Auth geo-resolve failed: %s", geo_exc)

                    # Create user via manager pipeline
                    user = UnifiedUser.objects.create_user(
                        email=email,
                        password=None,          # Sets unusable password hash
                        first_name=first_name,
                        last_name=last_name,
                        auth_provider=UnifiedUser.PROVIDER_GOOGLE,
                        is_verified=True,       # Google guarantees email ownership
                        is_active=True,         # Google users skip OTP activation
                        role=role,
                        country=geo_data.get('country', ''),
                        city=geo_data.get('city', ''),
                        state=geo_data.get('region', ''),
                    )

                    is_new = True
                    logger.info(
                        "🆕 Google Register: new user %s (member_id=%s, role=%s, country=%s)",
                        email, user.member_id, role, geo_data.get('country', 'Unknown')
                    )

                    # ── Wallet Provisioning (get_or_create) ────────────────
                    # ARCHITECTURAL REQUIREMENT: Google-registered users ALSO
                    # need a wallet. Every Fashionistar user — regardless of
                    # auth provider (email, phone, google) — MUST have an NGN
                    # wallet created at account creation time.
                    #
                    # INTEGRITY GUARANTEE: This provisioning is INSIDE the
                    # atomic block so that if wallet creation fails, user
                    # creation rolls back cleanly — no orphaned users without
                    # wallets (a critical financial data-integrity requirement).
                    try:
                        from apps.wallet.services import WalletProvisioningService  # noqa: PLC0415
                        WalletProvisioningService.ensure_wallet(
                            user, currency_code="NGN", request=request
                        )
                        logger.info(
                            "✅ Google Register: NGN wallet provisioned "
                            "[user_id=%s, role=%s]",
                            user.id, user.role,
                        )
                    except Exception as wallet_exc:
                        logger.error(
                            "❌ Google Register: wallet provisioning failed "
                            "[user_id=%s]: %s",
                            user.id, str(wallet_exc), exc_info=True,
                        )
                        raise  # Rolls back the whole atomic block

                    # ── Google Avatar → Cloudinary (fire-and-forget Celery) ──
                    # We download the Google CDN avatar and re-upload it to our
                    # Cloudinary account so we own the CDN path.
                    # The avatar field is updated after the Celery task finishes.
                    if google_avatar_url:
                        from apps.authentication.tasks import upload_google_avatar_to_cloudinary  # noqa: PLC0415
                        transaction.on_commit(
                            lambda: upload_google_avatar_to_cloudinary.delay(
                                str(user.pk), google_avatar_url
                            )
                        )

                    # Emit registration events
                    from apps.common.events import event_bus  # noqa: PLC0415
                    transaction.on_commit(
                        lambda: event_bus.emit(
                            'user.registered',
                            user_uuid=str(user.pk),
                            email=user.email,
                            role=user.role,
                            auth_provider='google',
                            member_id=user.member_id
                        )
                    )

                    # Success registration audit: Atomic dispatch on commit
                    transaction.on_commit(
                        lambda: auth_audit.log_register_success(actor=user, request=request)
                    )

            # ── 4. Update profile fields on returning Google users ─────────
            # We silently update name if Google changes them.
            if not is_new:
                update_fields = []
                if first_name and user.first_name != first_name:
                    user.first_name = first_name
                    update_fields.append('first_name')
                if last_name and user.last_name != last_name:
                    user.last_name = last_name
                    update_fields.append('last_name')

                if update_fields:
                    user.save(update_fields=update_fields)
                    logger.info("🔄 Google profile sync for user=%s", email)

            # ── 5. Token Generation & Login Audit ──────────────────────────
            refresh = RefreshToken.for_user(user)
            tokens = {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
            }

            # Update last_login
            from django.contrib.auth.models import update_last_login
            update_last_login(None, user)

            # Success login audit (for both new and existing users)
            # Use refresh token jti (stable session identifier) not access token jti
            transaction.on_commit(
                lambda: auth_audit.log_login_success(
                    actor=user,
                    request=request,
                    session_id=str(refresh.payload.get('jti', ''))
                )
            )

            return {
                'user': user,
                'tokens': tokens,
                'is_new': is_new,
            }

        except Exception as exc:
            # ── Failure Audit: Google Auth Processing Error ──────────────────
            # BUG FIX: The previous code had:
            #   except (ValueError, Exception): raise        ← catches EVERYTHING
            #   except Exception as exc: [audit code]        ← UNREACHABLE DEAD CODE
            # because `except (ValueError, Exception)` is equivalent to
            # `except Exception` (ValueError is a subclass of Exception).
            # The second except block could NEVER execute, so log_login_failed()
            # was NEVER called on Google auth failures.
            #
            # COMPLIANCE FIX: Google auth failures are now properly audited.
            # We use a nested try/except so the audit itself never crashes.
            try:
                auth_audit.log_login_failed(
                    email=email,
                    request=request,
                    reason=str(exc)[:200],
                )
            except Exception as audit_exc:
                logger.warning(
                    "⚠️ Google auth failure audit failed: %s", audit_exc
                )

            logger.error(
                "❌ Google Auth processing error: %s", exc, exc_info=True
            )
            raise Exception("Google authentication failed. Please try again.") from exc
