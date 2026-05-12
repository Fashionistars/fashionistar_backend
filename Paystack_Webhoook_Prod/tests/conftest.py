# Paystack_Webhoook_Prod/tests/conftest.py
"""
Paystack Webhook & Payments — Test fixtures
=============================================
Fixtures for testing:
  - Paystack webhook signature verification
  - Payment deposit flows
  - Bank account detail validation
  - Vendor withdrawal flows

Financial/payment tests MUST always mock external HTTP (Paystack API).
Never make real Paystack API calls in tests.
"""
import pytest
import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock


PAYSTACK_TEST_SECRET = 'sk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

SAMPLE_CHARGE_SUCCESS = {
    'event': 'charge.success',
    'data': {
        'id': 12345,
        'status': 'success',
        'reference': 'test_ref_charge_001',
        'amount': 500000,   # ₦5,000 in kobo
        'currency': 'NGN',
        'customer': {
            'email': 'customer@fashionistar-test.io',
            'id': 99,
        },
        'metadata': {
            'order_id': 'order-uuid-123',
        },
    },
}

SAMPLE_TRANSFER_SUCCESS = {
    'event': 'transfer.success',
    'data': {
        'id': 67890,
        'status': 'success',
        'transfer_code': 'TRF_test001',
        'amount': 100000,
        'currency': 'NGN',
        'recipient': {
            'type': 'nuban',
            'name': 'Test Vendor',
        },
    },
}


@pytest.fixture
def paystack_charge_payload():
    """Sample Paystack charge.success webhook payload."""
    return SAMPLE_CHARGE_SUCCESS


@pytest.fixture
def paystack_transfer_payload():
    """Sample Paystack transfer.success webhook payload."""
    return SAMPLE_TRANSFER_SUCCESS


@pytest.fixture
def signed_webhook_request(client, settings):
    """
    Returns a callable that posts a webhook payload with a valid
    Paystack HMAC-SHA512 signature header.

    Usage:
        response = signed_webhook_request(SAMPLE_CHARGE_SUCCESS)
        assert response.status_code == 200
    """
    settings.PAYSTACK_SECRET_KEY = PAYSTACK_TEST_SECRET

    def _post(payload: dict):
        payload_bytes = json.dumps(payload).encode('utf-8')
        signature = hmac.new(
            PAYSTACK_TEST_SECRET.encode('utf-8'),
            payload_bytes,
            hashlib.sha512,
        ).hexdigest()
        return client.post(
            '/webhooks/paystack/',
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )

    return _post


@pytest.fixture
def mock_paystack_api():
    """
    Generic mock for all Paystack API HTTP calls.
    Returns a MagicMock that simulates a successful Paystack API response.
    """
    with patch('requests.post') as mock_post, patch('requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': True, 'message': 'Successful'}
        mock_post.return_value = mock_response
        mock_get.return_value = mock_response
        yield {'post': mock_post, 'get': mock_get}
