# apps/authentication/tests/test_password_reset.py
"""
FASHIONISTAR — Password Reset & Session Comprehensive Test Suite
================================================================
Tests ALL v1 password + session endpoints with:
  ✅ Functional correctness (happy + error paths)
  ✅ Idempotency  — same token/OTP submitted twice
  ✅ Race conditions — two simultaneous confirmations
  ✅ Concurrency  — ThreadPoolExecutor (20 workers)
  ✅ transaction.atomic() integrity: rollback on failure
  ✅ Anti-enumeration: unknown users always return 200
  ✅ OTP-only pattern: no phone in phone-reset body
  ✅ Session & login-event endpoints covered

Run:
  pytest apps/authentication/tests/test_password_reset.py -v --tb=short -x
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.models import UnifiedUser


# ===========================================================================
# CONSTANTS
# ===========================================================================

RESET_REQUEST_URL        = "/api/v1/password/reset-request/"
RESET_PHONE_CONFIRM_URL  = "/api/v1/password/reset-phone-confirm/"
PASSWORD_CHANGE_URL      = "/api/v1/password/change/"
SESSION_LIST_URL         = "/api/v1/auth/sessions/"
SESSION_REVOKE_OTHERS    = "/api/v1/auth/sessions/revoke-others/"
LOGIN_EVENTS_URL         = "/api/v1/auth/login-events/"


def _reset_confirm_email_url(uidb64: str, token: str) -> str:
    return f"/api/v1/password/reset-confirm/{uidb64}/{token}/"


# ===========================================================================
# HELPERS
# ===========================================================================

def _email_user(email: str = "pwreset@example.com", pw: str = "OldPass123!") -> UnifiedUser:
    u = UnifiedUser.objects.create_user(email=email, password=pw)
    u.is_active = u.is_verified = True
    u.save(update_fields=["is_active", "is_verified"])
    return u


def _phone_user(phone: str = "+2348012345678", pw: str = "OldPass123!") -> UnifiedUser:
    u = UnifiedUser.objects.create_user(
        phone=phone, password=pw, auth_provider=UnifiedUser.PROVIDER_PHONE
    )
    u.is_active = u.is_verified = True
    u.save(update_fields=["is_active", "is_verified"])
    return u



def _email_token(user: UnifiedUser) -> tuple[str, str]:
    return urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user)


def _jwt(user: UnifiedUser) -> str:
    from rest_framework_simplejwt.tokens import RefreshToken
    return str(RefreshToken.for_user(user).access_token)


def _auth_client(user: UnifiedUser) -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {_jwt(user)}")
    return c


# ===========================================================================
# Bug 1 — Admin UserSession is_expired_badge (mark_safe regression guard)
# ===========================================================================

class TestIsExpiredBadge:
    """Admin is_expired_badge must NOT raise TypeError."""

    def test_active_badge(self, db):
        from apps.authentication.admin import UserSessionAdmin
        from apps.authentication.models import UserSession
        from django.contrib import admin as da
        sa = UserSessionAdmin(UserSession, da.site)
        m = MagicMock()
        m.expires_at = timezone.now() + timezone.timedelta(hours=1)
        result = sa.is_expired_badge(m)
        assert "ACTIVE" in str(result) and "10b981" in str(result)

    def test_expired_badge(self, db):
        from apps.authentication.admin import UserSessionAdmin
        from apps.authentication.models import UserSession
        from django.contrib import admin as da
        sa = UserSessionAdmin(UserSession, da.site)
        m = MagicMock()
        m.expires_at = timezone.now() - timezone.timedelta(hours=1)
        result = sa.is_expired_badge(m)
        assert "EXPIRED" in str(result) and "ef4444" in str(result)


# ===========================================================================
# Bug 2+3 — Password Reset Request (email context: reset_url + SITE_URL)
# ===========================================================================

@pytest.mark.django_db(transaction=True)
class TestPasswordResetRequest:
    """POST /api/v1/password/reset-request/"""

    def test_email_reset_sends_reset_url_not_reset_link(self, mock_email_task, mock_sms_task):
        """Template key must be 'reset_url', NOT 'reset_link'."""
        user = _email_user()
        APIClient().post(RESET_REQUEST_URL, {"email_or_phone": user.email}, format="json")
        assert mock_email_task.called
        ctx = mock_email_task.call_args[1].get("context") or mock_email_task.call_args[0][3]
        assert "reset_url" in ctx,  f"Expected 'reset_url', got keys: {list(ctx.keys())}"
        assert "SITE_URL"  in ctx,  f"Expected 'SITE_URL', got keys: {list(ctx.keys())}"
        assert ctx["reset_url"].startswith("http"), "reset_url must be a full URL"

    def test_phone_reset_dispatches_sms(self, mock_sms_task, mock_email_task):
        user = _phone_user()
        r = APIClient().post(RESET_REQUEST_URL, {"email_or_phone": str(user.phone)}, format="json")
        assert r.status_code == status.HTTP_200_OK
        assert mock_sms_task.called

    def test_unknown_email_returns_200_anti_enumeration(self):
        r = APIClient().post(RESET_REQUEST_URL, {"email_or_phone": "ghost@nowhere.invalid"}, format="json")
        assert r.status_code == status.HTTP_200_OK

    def test_missing_field_returns_400(self):
        assert APIClient().post(RESET_REQUEST_URL, {}, format="json").status_code == status.HTTP_400_BAD_REQUEST

    def test_idempotency_double_request_both_200(self, mock_email_task, mock_sms_task):
        user = _email_user()
        c = APIClient()
        for _ in range(2):
            assert c.post(RESET_REQUEST_URL, {"email_or_phone": user.email}, format="json").status_code == 200


# ===========================================================================
# Email Confirm
# ===========================================================================

@pytest.mark.django_db(transaction=True)
class TestPasswordResetConfirmEmail:
    """POST /api/v1/password/reset-confirm/<uidb64>/<token>/"""

    def test_valid_token_resets_password(self, mock_email_task, mock_sms_task):
        user = _email_user()
        uid, token = _email_token(user)
        r = APIClient().post(_reset_confirm_email_url(uid, token),
                             {"password": "NewSuperSecret1!", "password2": "NewSuperSecret1!"},
                             format="json")
        assert r.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password("NewSuperSecret1!")

    def test_bad_token_returns_400_with_code(self):
        user = _email_user()
        uid  = urlsafe_base64_encode(force_bytes(user.pk))
        r = APIClient().post(_reset_confirm_email_url(uid, "bad-token-xyz"),
                             {"password": "NewSuperSecret1!", "password2": "NewSuperSecret1!"},
                             format="json")
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert r.json().get("code") == "invalid_token"

    def test_mismatched_passwords_returns_400(self):
        user = _email_user()
        uid, token = _email_token(user)
        r = APIClient().post(_reset_confirm_email_url(uid, token),
                             {"password": "NewSuperSecret1!", "password2": "Different2!"},
                             format="json")
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_idempotency_same_token_twice(self, mock_email_task, mock_sms_task):
        """One-use token: second attempt after success must return 400."""
        user = _email_user()
        uid, token = _email_token(user)
        url = _reset_confirm_email_url(uid, token)
        pw = {"password": "NewSuperSecret1!", "password2": "NewSuperSecret1!"}
        r1 = APIClient().post(url, pw, format="json")
        r2 = APIClient().post(url, {"password": "AnotherNew2!", "password2": "AnotherNew2!"}, format="json")
        assert r1.status_code == 200
        assert r2.status_code == 400

    def test_atomic_rollback_on_weak_password(self):
        """Serializer rejects weak PW before service is called — hash stays unchanged."""
        user = _email_user()
        original = user.password
        uid, token = _email_token(user)
        APIClient().post(_reset_confirm_email_url(uid, token),
                         {"password": "123", "password2": "123"}, format="json")
        user.refresh_from_db()
        assert user.password == original

    def test_race_condition_same_token_two_threads(self, mock_email_task, mock_sms_task):
        """Exactly 1 thread wins; the other gets 400 (token consumed)."""
        user = _email_user()
        uid, token = _email_token(user)
        url = _reset_confirm_email_url(uid, token)
        pw  = {"password": "RaceWinner1!", "password2": "RaceWinner1!"}
        results = []
        barrier = threading.Barrier(2)

        def hit():
            barrier.wait()
            results.append(APIClient().post(url, pw, format="json").status_code)

        threads = [threading.Thread(target=hit) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(200) == 1, f"Expected 1 win, got: {results}"
        assert results.count(400) == 1


# ===========================================================================
# Bug 4 — Phone OTP-only Confirm (no phone in request body)
# ===========================================================================

@pytest.mark.django_db(transaction=True)
class TestPasswordResetConfirmPhone:
    """POST /api/v1/password/reset-phone-confirm/"""

    def test_valid_otp_resets_password(self):
        """Happy path: otp+password+password2 → 200. No phone in body."""
        user = _phone_user()
        with patch(
            "apps.authentication.services.password_service.sync_service."
            "OTPService.verify_by_otp_sync",
            return_value={"user_id": str(user.id), "purpose": "password_reset"},
        ):
            r = APIClient().post(RESET_PHONE_CONFIRM_URL, {
                "otp": "123456", "password": "PhoneNew1!", "password2": "PhoneNew1!",
            }, format="json")
        assert r.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password("PhoneNew1!")

    def test_phone_field_NOT_required(self):
        """Regression guard: sending no phone must NOT cause 'phone required' error."""
        with patch(
            "apps.authentication.services.password_service.sync_service."
            "OTPService.verify_by_otp_sync",
            return_value=None,          # OTP invalid — but serializer must pass
        ):
            r = APIClient().post(RESET_PHONE_CONFIRM_URL, {
                "otp": "000000", "password": "PhoneNew1!", "password2": "PhoneNew1!",
            }, format="json")
        # Should be 400 due to invalid OTP from service, NOT from "phone required"
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        errors = str(r.json())
        assert "phone" not in errors.lower() or "invalid" in errors.lower(), (
            "Serializer must not require phone field"
        )

    def test_invalid_otp_returns_400_invalid_otp_code(self):
        """verify_by_otp_sync returns None → service raises → 400 code=invalid_otp."""
        with patch(
            "apps.authentication.services.password_service.sync_service."
            "OTPService.verify_by_otp_sync",
            return_value=None,
        ):
            r = APIClient().post(RESET_PHONE_CONFIRM_URL, {
                "otp": "000000", "password": "PhoneNew1!", "password2": "PhoneNew1!",
            }, format="json")
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert r.json().get("code") == "invalid_otp"

    def test_non_digit_otp_rejected_by_serializer(self):
        r = APIClient().post(RESET_PHONE_CONFIRM_URL, {
            "otp": "ABCDEF", "password": "PhoneNew1!", "password2": "PhoneNew1!",
        }, format="json")
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_idempotency_otp_consumed_on_first_use(self):
        user = _phone_user()
        count = {"n": 0}

        def _once(*args, **kw):
            count["n"] += 1
            if count["n"] == 1:
                return {"user_id": str(user.id), "purpose": "password_reset"}
            return None

        with patch(
            "apps.authentication.services.password_service.sync_service."
            "OTPService.verify_by_otp_sync",
            side_effect=_once,
        ):
            r1 = APIClient().post(RESET_PHONE_CONFIRM_URL,
                                  {"otp": "123456", "password": "FirstPass1!", "password2": "FirstPass1!"},
                                  format="json")
            r2 = APIClient().post(RESET_PHONE_CONFIRM_URL,
                                  {"otp": "123456", "password": "SecondPass1!", "password2": "SecondPass1!"},
                                  format="json")
        assert r1.status_code == 200
        assert r2.status_code == 400

    def test_atomic_rollback_on_invalid_otp(self):
        """Password must NOT change when OTP fails — transaction.atomic ensures this."""
        user = _phone_user()
        orig = user.password
        with patch(
            "apps.authentication.services.password_service.sync_service."
            "OTPService.verify_by_otp_sync",
            return_value=None,
        ):
            APIClient().post(RESET_PHONE_CONFIRM_URL,
                             {"otp": "000000", "password": "Injected1!", "password2": "Injected1!"},
                             format="json")
        user.refresh_from_db()
        assert user.password == orig, "Password must NOT change on failed OTP"

    def test_race_otp_consumed_only_once(self):
        user = _phone_user()
        lock, consumed = threading.Lock(), {"done": False}

        def _atomic(*args, **kw):
            with lock:
                if not consumed["done"]:
                    consumed["done"] = True
                    return {"user_id": str(user.id), "purpose": "password_reset"}
            return None

        results, barrier = [], threading.Barrier(2)

        def hit():
            barrier.wait()
            with patch(
                "apps.authentication.services.password_service.sync_service."
                "OTPService.verify_by_otp_sync",
                side_effect=_atomic,
            ):
                r = APIClient().post(RESET_PHONE_CONFIRM_URL,
                                     {"otp": "123456", "password": "RacePass1!", "password2": "RacePass1!"},
                                     format="json")
            results.append(r.status_code)

        threads = [threading.Thread(target=hit) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count(200) == 1, f"Expected 1 win got: {results}"


# ===========================================================================
# Change Password
# ===========================================================================

@pytest.mark.django_db(transaction=True)
class TestChangePassword:
    """POST /api/v1/password/change/"""

    def test_success(self, mock_email_task, mock_sms_task):
        user = _email_user()
        r = _auth_client(user).post(PASSWORD_CHANGE_URL, {
            "old_password": "OldPass123!", "new_password": "Changed1!",
            "confirm_password": "Changed1!",
        }, format="json")
        assert r.status_code == 200
        user.refresh_from_db()
        assert user.check_password("Changed1!")

    def test_wrong_old_password_returns_400(self):
        user = _email_user()
        r = _auth_client(user).post(PASSWORD_CHANGE_URL, {
            "old_password": "WrongOld!", "new_password": "Changed1!",
            "confirm_password": "Changed1!",
        }, format="json")
        assert r.status_code == 400

    def test_unauthenticated_returns_401(self):
        r = APIClient().post(PASSWORD_CHANGE_URL, {
            "old_password": "X", "new_password": "Y", "confirm_password": "Y",
        }, format="json")
        assert r.status_code in (401, 403)

    def test_atomic_block_integrity(self, mock_email_task, mock_sms_task):
        user = _email_user()
        with transaction.atomic():
            r = _auth_client(user).post(PASSWORD_CHANGE_URL, {
                "old_password": "OldPass123!", "new_password": "Atomic1!",
                "confirm_password": "Atomic1!",
            }, format="json")
        assert r.status_code == 200
        user.refresh_from_db()
        assert user.check_password("Atomic1!")


# ===========================================================================
# Session & Login-Event Views
# ===========================================================================

@pytest.mark.django_db(transaction=True)
class TestSessionViews:
    """GET/DELETE/POST on session endpoints — all require IsVerifiedUser."""

    def test_session_list_200(self):
        user = _email_user()
        r = _auth_client(user).get(SESSION_LIST_URL)
        assert r.status_code == 200
        # CustomJSONRenderer wraps: {success, message, data: {results: [...]}}
        body = r.json()
        payload = body.get("data", body)  # unwrap renderer envelope if present
        assert "results" in payload

    def test_session_list_unauthenticated_401(self):
        assert APIClient().get(SESSION_LIST_URL).status_code in (401, 403)

    def test_revoke_others_200(self):
        user = _email_user()
        r = _auth_client(user).post(SESSION_REVOKE_OTHERS)
        assert r.status_code == 200
        body = r.json()
        payload = body.get("data", body)
        assert "terminated_count" in payload

    def test_login_events_200(self):
        user = _email_user()
        r = _auth_client(user).get(LOGIN_EVENTS_URL)
        assert r.status_code == 200
        body = r.json()
        payload = body.get("data", body)
        assert "results" in payload

    def test_login_events_unauthenticated_401(self):
        assert APIClient().get(LOGIN_EVENTS_URL).status_code in (401, 403)

    def test_revoke_nonexistent_session_404(self):
        user = _email_user()
        r = _auth_client(user).delete("/api/v1/auth/sessions/999999/")
        assert r.status_code == 404


# ===========================================================================
# Concurrency Stress — 20 simultaneous workers
# ===========================================================================

@pytest.mark.django_db(transaction=True)
class TestConcurrencyStress:
    NUM = 20

    def test_20_concurrent_reset_requests_all_200(self, mock_email_task, mock_sms_task):
        user = _email_user()
        c = APIClient()

        def hit():
            return c.post(RESET_REQUEST_URL, {"email_or_phone": user.email}, format="json").status_code

        with ThreadPoolExecutor(max_workers=self.NUM) as ex:
            codes = [f.result() for f in as_completed(ex.submit(hit) for _ in range(self.NUM))]

        assert all(s == 200 for s in codes), f"Not all 200: {codes}"

    def test_20_concurrent_phone_confirm_only_1_wins(self, mock_email_task, mock_sms_task):
        """
        Concurrent OTP: exactly 1 of 20 threads should win.
        Uses a module-level side_effect function (thread-safe lock) rather than
        per-thread patching, which doesn't work across thread boundaries.
        """
        user = _phone_user()
        lock, consumed = threading.Lock(), {"done": False}
        codes = []

        def _atomic_verify(*a, **kw):
            with lock:
                if not consumed["done"]:
                    consumed["done"] = True
                    return {"user_id": str(user.id), "purpose": "password_reset"}
            return None

        def hit():
            r = APIClient().post(RESET_PHONE_CONFIRM_URL,
                                 {"otp": "123456", "password": "ConcPass1!", "password2": "ConcPass1!"},
                                 format="json")
            codes.append(r.status_code)

        # Patch once at module level so ALL threads share the same mock
        with patch(
            "apps.authentication.services.password_service.sync_service."
            "OTPService.verify_by_otp_sync",
            side_effect=_atomic_verify,
        ):
            with ThreadPoolExecutor(max_workers=self.NUM) as ex:
                futures = [ex.submit(hit) for _ in range(self.NUM)]
                for f in as_completed(futures):
                    f.result()  # propagate any exceptions

        assert codes.count(200) == 1, f"Expected exactly 1 success, got: {codes}"
