import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.payment.models import PaymentIntent, PaymentIntentStatus, PaymentPurpose, PaymentWebhookEvent
from apps.payment.services import PaystackClient, PaystackWebhookService


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
