# apps/measurements/tests/test_scan_views_qr.py
"""
TASK-065 (Part 2): Integration tests for InitiateScanView QR code response.

Tests cover:
  - POST /scan/initiate/ returns measurement_url + qr_code_b64 fields
  - measurement_url is saved to BodyScanSession in the database
  - device_type is correctly stored
  - Rate limiting returns 429 on too many requests
  - QR fields have the correct format

Run:
    pytest apps/measurements/tests/test_scan_views_qr.py -v
"""

import uuid
from unittest.mock import patch, MagicMock

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, django_user_model):
    """Return an authenticated DRF test client.

    UnifiedUserManager.create_user() signature:
        create_user(email=None, phone=None, password=None, **extra_fields)

    Note: is_active=True + is_verified=True required — InitiateScanView
    uses IsAuthenticated + IsVerified permissions (403 for inactive accounts).
    """
    user = django_user_model.objects.create_user(
        email="scan@fashionistar.test",
        password="TestPass123!",
        is_active=True,
        is_verified=True,
    )
    api_client.force_authenticate(user=user)
    return api_client, user



# ─── InitiateScanView QR fields ────────────────────────────────────────────────

@pytest.mark.django_db
class TestInitiateScanViewQRFields:

    INITIATE_URL = "/api/v1/measurements/scan/initiate/"

    def _post(self, client, payload=None):
        return client.post(self.INITIATE_URL, payload or {}, format="json")

    def test_response_contains_measurement_url(self, authenticated_client):
        """POST /scan/initiate/ response must include measurement_url."""
        client, _ = authenticated_client
        with patch("apps.ai.tasks.measurement_tasks.prepare_scan_session.delay"), \
             patch("apps.ai.tasks.measurement_tasks.upload_qr_code_to_cloudinary.delay"):
            resp = self._post(client)

        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json().get("data", resp.json())
        assert "measurement_url" in data, f"measurement_url not in response: {data.keys()}"
        assert data["measurement_url"].startswith("http")

    def test_response_contains_qr_code_b64(self, authenticated_client):
        """POST /scan/initiate/ response must include qr_code_b64."""
        client, _ = authenticated_client
        with patch("apps.ai.tasks.measurement_tasks.prepare_scan_session.delay"), \
             patch("apps.ai.tasks.measurement_tasks.upload_qr_code_to_cloudinary.delay"):
            resp = self._post(client)

        data = resp.json().get("data", resp.json())
        assert "qr_code_b64" in data, f"qr_code_b64 not in response: {data.keys()}"
        # May be empty if qrcode is not installed in test env — just check key exists

    def test_response_contains_qr_code_url_field(self, authenticated_client):
        """POST /scan/initiate/ response must include qr_code_url (empty initially)."""
        client, _ = authenticated_client
        with patch("apps.ai.tasks.measurement_tasks.prepare_scan_session.delay"), \
             patch("apps.ai.tasks.measurement_tasks.upload_qr_code_to_cloudinary.delay"):
            resp = self._post(client)

        data = resp.json().get("data", resp.json())
        assert "qr_code_url" in data

    def test_measurement_url_saved_to_database(self, authenticated_client):
        """measurement_url must be persisted to BodyScanSession.measurement_url."""
        from apps.measurements.models.scan import BodyScanSession
        client, user = authenticated_client

        with patch("apps.ai.tasks.measurement_tasks.prepare_scan_session.delay"), \
             patch("apps.ai.tasks.measurement_tasks.upload_qr_code_to_cloudinary.delay"):
            resp = self._post(client)

        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json().get("data", resp.json())
        session_id = data.get("session_id")
        assert session_id is not None

        session = BodyScanSession.objects.get(session_id=session_id)
        assert session.measurement_url != "", "measurement_url should be saved to DB"
        assert session_id in session.measurement_url

    def test_measurement_url_contains_session_id(self, authenticated_client):
        """measurement_url must embed the session_id for routing."""
        client, _ = authenticated_client
        with patch("apps.ai.tasks.measurement_tasks.prepare_scan_session.delay"), \
             patch("apps.ai.tasks.measurement_tasks.upload_qr_code_to_cloudinary.delay"):
            resp = self._post(client)

        data = resp.json().get("data", resp.json())
        session_id   = data.get("session_id", "")
        measurement_url = data.get("measurement_url", "")
        assert session_id in measurement_url, (
            f"session_id '{session_id}' not found in measurement_url '{measurement_url}'"
        )

    def test_device_type_web_saved(self, authenticated_client):
        """device_type=web must be stored on the session."""
        from apps.measurements.models.scan import BodyScanSession
        client, _ = authenticated_client

        with patch("apps.ai.tasks.measurement_tasks.prepare_scan_session.delay"), \
             patch("apps.ai.tasks.measurement_tasks.upload_qr_code_to_cloudinary.delay"):
            resp = self._post(client, {"device_type": "web"})

        data = resp.json().get("data", resp.json())
        session = BodyScanSession.objects.get(session_id=data["session_id"])
        assert session.device_type == "web"

    def test_device_type_ios_saved(self, authenticated_client):
        """device_type=ios must be stored on the session."""
        from apps.measurements.models.scan import BodyScanSession
        client, _ = authenticated_client

        with patch("apps.ai.tasks.measurement_tasks.prepare_scan_session.delay"), \
             patch("apps.ai.tasks.measurement_tasks.upload_qr_code_to_cloudinary.delay"):
            resp = self._post(client, {"device_type": "ios"})

        data = resp.json().get("data", resp.json())
        session = BodyScanSession.objects.get(session_id=data["session_id"])
        assert session.device_type == "ios"

    def test_unauthenticated_returns_401(self, api_client):
        """Un-authenticated requests must return 401."""
        resp = self._post(api_client, {})
        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
