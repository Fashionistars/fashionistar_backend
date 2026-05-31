from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import TestCase
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestPublicEngagementViews(TestCase):
    def test_newsletter_signup_queues_support_notification(self):
        with patch(
            "apps.common.tasks.engagement.send_public_engagement_email.apply_async"
        ) as task_mock:
            with self.captureOnCommitCallbacks(execute=True):
                response = APIClient().post(
                    "/api/v1/public/newsletter/",
                    {"email": "newsletter@example.com", "source": "homepage"},
                    format="json",
                )

        assert response.status_code == 202
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["email"] == "newsletter@example.com"
        task_mock.assert_called_once()

    def test_waitlist_signup_queues_support_notification(self):
        with patch(
            "apps.common.tasks.engagement.send_public_engagement_email.apply_async"
        ) as task_mock:
            with self.captureOnCommitCallbacks(execute=True):
                response = APIClient().post(
                    "/api/v1/public/waitlist/",
                    {"email": "waitlist@example.com", "source": "mobile_waitlist"},
                    format="json",
                )

        assert response.status_code == 202
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["source"] == "mobile_waitlist"
        task_mock.assert_called_once()

    def test_contact_submission_queues_support_notification(self):
        with patch(
            "apps.common.tasks.engagement.send_public_engagement_email.apply_async"
        ) as task_mock:
            with self.captureOnCommitCallbacks(execute=True):
                response = APIClient().post(
                    "/api/v1/public/contact/",
                    {
                        "full_name": "Ada Okafor",
                        "email": "ada@example.com",
                        "phone": "+2348012345678",
                        "subject": "Vendor enquiry",
                        "message": "I would like to discuss a custom order for an event.",
                        "vendor": "lagos-style-house",
                        "inquiry_type": "custom_order",
                        "page_url": "https://fashionistar.net/contact-us?vendor=lagos-style-house",
                    },
                    format="json",
                )

        assert response.status_code == 202
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["email"] == "ada@example.com"
        task_mock.assert_called_once()

    def test_invalid_public_submission_returns_400(self):
        cases = [
            ("/api/v1/public/newsletter/", {"email": "not-an-email"}),
            ("/api/v1/public/waitlist/", {"email": ""}),
            (
                "/api/v1/public/contact/",
                {
                    "full_name": "A",
                    "email": "bad",
                    "message": "short",
                },
            ),
        ]

        for path, body in cases:
            response = APIClient().post(path, body, format="json")

            assert response.status_code == 400
            payload = response.json()
            assert payload["success"] is False
            assert payload["code"] == "validation_error"
