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
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        """
        Verify the Google ID-token, find-or-create the user, and return JWT tokens.

        Args:
            token:      The ``id_token`` returned by Google to the Next.js frontend.
            role:       The role to assign on first registration ('client' or 'vendor').
            ip_address: Forwarded for the LoginAuditLog (optional).
            user_agent: HTTP User-Agent string (optional).

        Returns:
            {
                "user":   <UnifiedUser instance>,
                "tokens": {"access": "...", "refresh": "..."},
                "is_new": bool,
            }

        Raises:
            ValueError: on invalid token.
            Exception:  on unexpected errors.
        """
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        from apps.authentication.models import UnifiedUser
        from rest_framework_simplejwt.tokens import RefreshToken

        try:
            # ── 1. Verify token with Google ────────────────────────────────
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

            # Normalise email domain to lowercase only for email (phone remains unchanged)
            from django.contrib.auth.base_user import BaseUserManager as _BUM
            if email and "@" in email:
                email = _BUM.normalize_email(email)

            # ── 2. Extract rich profile data ───────────────────────────────
            first_name        = id_info.get('given_name', '')   or ''
            last_name         = id_info.get('family_name', '')  or ''
            full_name         = id_info.get('name', '')         or ''
            google_avatar_url = id_info.get('picture', '')      or ''
            locale            = id_info.get('locale', '')        or ''
            google_sub        = id_info.get('sub', '')           or ''  # Google's stable user ID

            logger.info(
                "🔍 Google token verified — email=%s sub=%s", email, google_sub
            )

        except ValueError as exc:
            logger.error("❌ Google token verification failed: %s", exc)
            raise ValueError("Invalid or expired Google Token.") from exc
        except Exception as exc:
            logger.error("❌ Unexpected error during Google token verification: %s", exc, exc_info=True)
            raise Exception("Google authentication failed. Please try again.") from exc

        try:
            # ── 3. Find or Create user ─────────────────────────────────────
            is_new = False

            try:
                user = UnifiedUser.objects.get(email=email)
                logger.info("✅ Google Login: existing user %s", email)

            except UnifiedUser.DoesNotExist:
                # New user — create via create_user() to go through the full
                # manager pipeline: member_id generation, unusable password,
                # full_clean() validation.
                with transaction.atomic():
                    user = UnifiedUser.objects.create_user(
                        email=email,
                        password=None,          # Sets unusable password hash
                        first_name=first_name,
                        last_name=last_name,
                        auth_provider=UnifiedUser.PROVIDER_GOOGLE,
                        is_verified=True,       # Google guarantees email ownership
                        is_active=True,         # Google users skip OTP activation
                        role=role,
                    )

                    is_new = True
                    logger.info(
                        "🆕 Google Register: new user %s (member_id=%s, role=%s)",
                        email, user.member_id, role,
                    )

                    # ── 4. Google Avatar → Cloudinary (fire-and-forget Celery) ──
                    # We download the Google CDN avatar and re-upload it to our
                    # Cloudinary account so we own the CDN path.
                    # The avatar field is updated after the Celery task finishes.
                    if google_avatar_url:
                        try:
                            from apps.authentication.tasks import (
                                upload_google_avatar_to_cloudinary,
                            )
                            transaction.on_commit(
                                lambda: upload_google_avatar_to_cloudinary.delay(
                                    str(user.pk), google_avatar_url
                                )
                            )
                            logger.info(
                                "📸 Scheduled Google avatar Cloudinary upload for user=%s",
                                email,
                            )
                        except Exception as avatar_exc:
                            # Non-fatal — user is already created
                            logger.warning(
                                "⚠️ Could not schedule avatar upload for %s: %s",
                                email, avatar_exc,
                            )

                    # ── 5. EventBus — emit user.registered ────────────────────
                    try:
                        from apps.common.events import event_bus

                        def _emit():
                            event_bus.emit('user.registered', {
                                'user_id':  str(user.pk),
                                'email':    user.email,
                                'role':     user.role,
                                'provider': 'google',
                                'member_id': user.member_id,
                            })

                        transaction.on_commit(_emit)
                    except Exception as event_exc:
                        logger.warning(
                            "⚠️ EventBus emit failed for user %s: %s", email, event_exc
                        )

            # ── 6. Update profile fields on returning Google users ─────────
            # We silently update name + avatar URL if Google changes them.
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
                    logger.info(
                        "🔄 Updated profile for returning Google user=%s fields=%s",
                        email, update_fields,
                    )

            # ── 7. Issue JWT tokens ────────────────────────────────────────
            refresh = RefreshToken.for_user(user)
            tokens = {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
            }

            return {
                'user':   user,
                'tokens': tokens,
                'is_new': is_new,
            }

        except (ValueError, Exception):
            raise
        except Exception as exc:
            logger.error(
                "❌ Unexpected error in SyncGoogleAuthService: %s", exc, exc_info=True
            )
            raise Exception("Google authentication failed.") from exc
