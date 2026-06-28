# apps/authentication/tests/test_user_session.py
"""
UserSession Unit & Integration Tests.
Covers session creation, client-context parsing, and geo-resolution.
"""
import pytest
from unittest.mock import patch
from rest_framework_simplejwt.tokens import RefreshToken
from apps.authentication.models import UserSession

@pytest.mark.django_db
class TestUserSessionCreation:
    """Tests session instantiation via UserSession.create_from_token."""

    def test_create_from_token_success(self, registered_verified_user):
        """Should successfully build a session from a RefreshToken with default context."""
        refresh = RefreshToken.for_user(registered_verified_user)
        session = UserSession.create_from_token(
            user=registered_verified_user,
            refresh_token=refresh,
            request=None
        )

        assert session.user == registered_verified_user
        assert session.jti == str(refresh.payload["jti"])
        assert session.expires_at is not None
        assert session.client_type == UserSession.CLIENT_UNKNOWN
        assert session.device_name == "Unknown Device"

    def test_create_from_token_with_request_context(self, rf, registered_verified_user):
        """Should parse IP address, User-Agent, and client platform from Request META."""
        request = rf.get("/api/v1/auth/login/")
        request.META["REMOTE_ADDR"] = "192.0.2.2"
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        request.META["HTTP_X_CLIENT_PLATFORM"] = "Windows"

        refresh = RefreshToken.for_user(registered_verified_user)
        session = UserSession.create_from_token(
            user=registered_verified_user,
            refresh_token=refresh,
            request=request
        )

        assert session.ip_address == "192.0.2.2"
        assert session.user_agent == request.META["HTTP_USER_AGENT"]
        assert "Chrome" in session.device_name or "Windows" in session.device_name or "Other" in session.device_name
        assert session.os_family == "Windows" or session.os_family == "Other"

    def test_create_from_token_with_geo_resolution(self, rf, registered_verified_user):
        """Should resolve geo-location parameters using the canonical resolver."""
        request = rf.get("/api/v1/auth/login/")
        request.META["REMOTE_ADDR"] = "8.8.8.8"

        mock_geo = {
            "country": "United States",
            "country_code": "US",
            "city": "Mountain View",
        }

        with patch("apps.audit_logs.services.audit._resolve_geo", return_value=mock_geo):
            refresh = RefreshToken.for_user(registered_verified_user)
            session = UserSession.create_from_token(
                user=registered_verified_user,
                refresh_token=refresh,
                request=request
            )

        assert session.country == "United States"
        assert session.country_code == "US"
        assert session.city == "Mountain View"
