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
  5. **Google avatar** → schedule a Celery task to download and re-upload
     the Google profile picture to Cloudinary (our Cloudinary CDN).
     The avatar URL is stored as the Cloudinary HTTPS secure_url after
     the webhook fires, so the user is never served a Google-controlled URL.
  6. **EventBus** → emit ``user.registered`` for new users so the welcome
     email, analytics increment, and any future subscribers are triggered
     in a fire-and-forget fashion via ``transaction.on_commit``.

Returns:
    dict with ``user`` (UnifiedUser instance) and ``tokens`` (access + refresh).
"""

import logging
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

        # ── 1. Token Verification ──────────────────────────────────────────
        try:
            id_info = google_id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )

            email = id_info.get('email')
            if not email:
                raise ValueError("Email not found in Google Token.")

            if not id_info.get('email_verified', False):
                raise ValueError("Google email is not verified.")

            # Normalise email domain
            from django.contrib.auth.base_user import BaseUserManager as _BUM
            if email and "@" in email:
                email = _BUM.normalize_email(email)

            # ── 2. Data Extraction ─────────────────────────────────────────
            first_name        = id_info.get('given_name', '')   or ''
            last_name         = id_info.get('family_name', '')  or ''
            google_avatar_url = id_info.get('picture', '')      or ''
            google_sub        = id_info.get('sub', '')           or ''

            logger.info("🔍 Google token verified: email=%s", email)

        except ValueError as exc:
            logger.error("❌ Google token verification failed: %s", exc)
            raise ValueError("Invalid or expired Google Token.") from exc
        except Exception as exc:
            logger.error("❌ Google Auth Failure: %s", exc, exc_info=True)
            raise Exception("Google authentication failed.") from exc

        # ── 3. Find or Create User ─────────────────────────────────────────
        try:
            is_new = False
            user = None

            try:
                user = UnifiedUser.objects.get(email=email)
                logger.info("✅ Google Login: existing user %s", email)
            except UnifiedUser.DoesNotExist:
                with transaction.atomic():
                    # Resolve geo-data for the new account
                    ip_address = None
                    if request:
                        # Extract IP if request object provided
                        from apps.audit_logs.services.audit import _get_client_ip
                        ip_address = _get_client_ip(request)

                    geo_data = {}
                    if ip_address:
                        try:
                            from apps.audit_logs.services.audit import _resolve_geo
                            geo_data = _resolve_geo(ip_address) or {}
                        except Exception as geo_exc:
                            logger.warning("⚠️ Google Auth geo-resolve failed: %s", geo_exc)

                    # Create user via manager pipeline
                    user = UnifiedUser.objects.create_user(
                        email=email,
                        password=None,
                        first_name=first_name,
                        last_name=last_name,
                        auth_provider=UnifiedUser.PROVIDER_GOOGLE,
                        is_verified=True,
                        is_active=True,
                        role=role,
                        country=geo_data.get('country', ''),
                        city=geo_data.get('city', ''),
                        state=geo_data.get('region', ''),
                    )
                    is_new = True

                    # ── 4. Avatar & Events ──────────────────────────────────
                    if google_avatar_url:
                        from apps.authentication.tasks import upload_google_avatar_to_cloudinary
                        transaction.on_commit(
                            lambda: upload_google_avatar_to_cloudinary.delay(str(user.pk), google_avatar_url)
                        )

                    # Emit registration events
                    from apps.common.events import event_bus
                    transaction.on_commit(
                        lambda: event_bus.emit(
                            'user.registered',
                            user_uuid=str(user.pk),
                            email=user.email,
                            role=user.role,
                            auth_provider='google'
                        )
                    )

                    # Success registration audit: Atomic dispatch on commit
                    transaction.on_commit(
                        lambda: auth_audit.log_register_success(actor=user, request=request)
                    )

            # ── 5. Profile Sync (Existing Users) ───────────────────────────
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

            # ── 6. Token Generation & Login Audit ──────────────────────────
            refresh = RefreshToken.for_user(user)
            tokens = {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
            }

            # Update last_login
            from django.contrib.auth.models import update_last_login
            update_last_login(None, user)

            # Success login audit (for both new and existing users)
            transaction.on_commit(
                lambda: auth_audit.log_login_success(
                    actor=user,
                    request=request,
                    session_id=str(refresh.payload.get('jti'))
                )
            )

            return {
                'user': user,
                'tokens': tokens,
                'is_new': is_new,
            }

        except Exception as exc:
            # Audit failed login attempt if possible
            if email:
                auth_audit.log_login_failed(email=email, request=request, reason=str(exc))
            
            logger.error("❌ Google Auth processing error: %s", exc, exc_info=True)
            raise
