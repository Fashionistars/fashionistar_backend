import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.http import ProviderTimeoutError
from apps.payment.models import (
    PaymentIntent,
    PaymentIntentStatus,
    PaymentProviderLog,
    PaymentPurpose,
    PaymentWebhookEvent,
)
from apps.payment.orchestrator import PaymentOrchestrator
from apps.payment.services import PaystackClient, PaystackWebhookService, PaymentIntentService
from apps.providers.Payment.paystack import PaystackClient as RegistryPaystackClient


class TimeoutPaystackTransport:
    def request(self, *args, **kwargs):
        raise ProviderTimeoutError(
            provider="paystack",
            action=kwargs.get("action", "transaction.initialize"),
            message="provider timed out",
            reference=kwargs.get("reference", ""),
        )


class CapturePaystackTransport:
    def __init__(self):
        self.last_json = None

    def request(self, *args, **kwargs):
        self.last_json = kwargs.get("json")

        class Response:
            data = {
                "status": True,
                "data": {
                    "reference": "PAYSTACK-CAPTURE-REF",
                    "authorization_url": "https://paystack.test/checkout",
                    "access_code": "ACCESS123",
                },
            }

        return Response()


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

    def test_initialize_transaction_sends_top_level_callback_url(self):
        transport = CapturePaystackTransport()

        with patch.object(PaystackClient, "_sync_client", return_value=transport):
            PaymentIntentService.initialize_paystack(
                user=self.user,
                amount=Decimal("1500.00"),
                purpose=PaymentPurpose.ORDER_PAYMENT,
                order_id="ORDER-123",
                metadata={
                    "selected_percent": 100,
                    "payment_path": "gateway",
                },
                idempotency_key="idem-callback-001",
            )

        self.assertIsNotNone(transport.last_json)
        self.assertIn("callback_url", transport.last_json)
        self.assertTrue(str(transport.last_json["callback_url"]).endswith("/client/dashboard/orders/ORDER-123/confirmation"))

    def test_wallet_fund_view_initializes_topup_without_missing_idempotency_key(self):
        transport = CapturePaystackTransport()
        client = APIClient()
        client.force_authenticate(user=self.user)

        with patch.object(PaystackClient, "_sync_client", return_value=transport):
            response = client.post(
                "/api/v1/payment/wallet/fund/",
                {
                    "amount": "1500.00",
                    "purpose": PaymentPurpose.WALLET_TOPUP,
                    "provider": "paystack",
                    "currency": "NGN",
                    "metadata": {"source": "test-wallet-topup"},
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json().get("data", {})
        self.assertEqual(payload.get("authorization_url"), "https://paystack.test/checkout")
        self.assertEqual(PaymentIntent.objects.filter(user=self.user, purpose=PaymentPurpose.WALLET_TOPUP).count(), 2)

    def test_orchestrator_paystack_initialize_accepts_callback_url(self):
        transport = CapturePaystackTransport()

        with patch.object(RegistryPaystackClient, "_sync", return_value=transport):
            response = PaymentOrchestrator.for_provider("paystack").initialize_payment(
                email="client@example.com",
                amount=Decimal("1500.00"),
                reference="ORCH-CALLBACK-001",
                currency="NGN",
                callback_url="http://localhost:3000/client/dashboard/orders/ORDER-123/confirmation",
                metadata={"purpose": "order_payment"},
            )

        self.assertTrue(response["status"])
        self.assertIsNotNone(transport.last_json)
        self.assertIn("callback_url", transport.last_json)
        self.assertEqual(
            transport.last_json["metadata"]["callback_url"],
            "http://localhost:3000/client/dashboard/orders/ORDER-123/confirmation",
        )

    def test_orchestrator_paystack_callback_url_overrides_stale_metadata(self):
        transport = CapturePaystackTransport()

        with patch.object(RegistryPaystackClient, "_sync", return_value=transport):
            PaymentOrchestrator.for_provider("paystack").initialize_payment(
                email="client@example.com",
                amount=Decimal("1500.00"),
                reference="ORCH-CALLBACK-OVERRIDE-001",
                currency="NGN",
                callback_url="http://localhost:3000/client/dashboard/orders/ORDER-456/confirmation",
                metadata={
                    "purpose": "order_payment",
                    "callback_url": "https://aeration-scabby-navy.ngrok-free.dev/client/dashboard/orders/ORDER-456/confirmation",
                },
            )

        self.assertIsNotNone(transport.last_json)
        self.assertEqual(
            transport.last_json["callback_url"],
            "http://localhost:3000/client/dashboard/orders/ORDER-456/confirmation",
        )
        self.assertEqual(
            transport.last_json["metadata"]["callback_url"],
            "http://localhost:3000/client/dashboard/orders/ORDER-456/confirmation",
        )
