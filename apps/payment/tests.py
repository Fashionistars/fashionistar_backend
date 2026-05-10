import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.common.http import ProviderTimeoutError
from apps.payment.models import (
    PaymentIntent,
    PaymentIntentStatus,
    PaymentProviderLog,
    PaymentPurpose,
    PaymentWebhookEvent,
)
from apps.payment.services import PaystackClient, PaystackWebhookService, PaymentIntentService


class TimeoutPaystackTransport:
    def request(self, *args, **kwargs):
        raise ProviderTimeoutError(
            provider="paystack",
            action=kwargs.get("action", "transaction.initialize"),
            message="provider timed out",
            reference=kwargs.get("reference", ""),
        )


class PaystackWebhookServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="paystack-client@example.com", password="StrongPass123!", role="client")
        self.intent = PaymentIntent.objects.create(
            user=self.user,
            purpose=PaymentPurpose.WALLET_TOPUP,
            amount=Decimal("2000.00"),
            currency="NGN",
            reference="PAYSTACK-REF-001",
        )

    def _signature(self, payload: bytes) -> str:
        return hmac.new(settings.PAYSTACK_SECRET_KEY.encode("utf-8"), payload, hashlib.sha512).hexdigest()

    def test_paystack_signature_validation(self):
        payload = b'{"event":"charge.success"}'
        self.assertTrue(PaystackClient.verify_signature(payload, self._signature(payload)))
        self.assertFalse(PaystackClient.verify_signature(payload, "bad-signature"))

    def test_webhook_replay_is_idempotent(self):
        payload = json.dumps({"event": "charge.success", "data": {"reference": "PAYSTACK-REF-001", "id": 123}}).encode("utf-8")
        signature = self._signature(payload)

        first = PaystackWebhookService.process(raw_payload=payload, signature=signature)
        second = PaystackWebhookService.process(raw_payload=payload, signature=signature)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 1)
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentIntentStatus.SUCCEEDED)

    @patch.object(PaystackClient, "_sync_client", return_value=TimeoutPaystackTransport())
    def test_initialize_timeout_does_not_create_partial_payment_intent(self, _mock_client):
        before_count = PaymentIntent.objects.count()

        with self.assertRaises(ValidationError):
            PaymentIntentService.initialize_paystack(
                user=self.user,
                amount=Decimal("1500.00"),
                purpose=PaymentPurpose.WALLET_TOPUP,
                idempotency_key="idem-timeout-001",
            )

        self.assertEqual(PaymentIntent.objects.count(), before_count)
        failure_log = PaymentProviderLog.objects.filter(
            provider="paystack",
            action="transaction.initialize",
            success=False,
        ).latest("created_at")
        self.assertIn("provider timed out", failure_log.error_message)
