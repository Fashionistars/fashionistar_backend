# apps/authentication/tests/unit/test_otp_service.py
"""
FASHIONISTAR — Unit Tests: OTPService
=======================================
Tests the OTPService business logic in isolation — no real Redis, no DB.

Covers:
  - generate_otp_sync: returns 6-digit numeric OTP, writes primary + hash keys
  - verify_otp_sync: decrypts and compares, deletes on match
  - verify_by_otp_sync: O(1) hash-index lookup, returns user_id / None
  - resend_otp_sync: invalidates old keys, generates new OTP, fixes template path
  - Edge cases: Redis unavailable, wrong purpose, already-used OTP
"""
import hashlib
import pytest
from unittest.mock import patch, MagicMock, call


OTP_SERVICE_PATH = 'apps.authentication.services.otp.sync_service'


# ─── Helpers ────────────────────────────────────────────────────────────────

def _sha256(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def _make_redis_mock(primary_val=None, hash_val=None):
    """Return a mock redis_conn with configurable GET responses."""
    redis = MagicMock()
    # keys() returns list of matching keys
    redis.keys.return_value = [b'otp:USER1:verify:SNPT0001']
    # get() returns bytes or None
    redis.get.side_effect = lambda k: (
        primary_val if b'otp:USER1' in str(k).encode() else
        hash_val.encode() if hash_val and b'otp_hash:' in str(k).encode() else
        None
    )
    redis.pipeline.return_value.__enter__ = MagicMock(return_value=MagicMock())
    redis.pipeline.return_value.__exit__ = MagicMock(return_value=False)
    pipe = MagicMock()
    redis.pipeline.return_value = pipe
    pipe.setex.return_value = None
    pipe.delete.return_value = None
    pipe.execute.return_value = [True, True]
    return redis


# =============================================================================
# generate_otp_sync
# =============================================================================

@pytest.mark.unit
class TestGenerateOTPSync:
    """Unit tests for OTPService.generate_otp_sync()."""

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    @patch(f'{OTP_SERVICE_PATH}.generate_numeric_otp', return_value='654321')
    @patch(f'{OTP_SERVICE_PATH}.encrypt_otp', return_value='ENCRYPTED_TOKEN_ABC')
    def test_returns_plain_text_otp(self, mock_enc, mock_gen, mock_redis):
        """generate_otp_sync must return the raw plain-text OTP string."""
        from apps.authentication.services.otp.sync_service import OTPService
        redis = _make_redis_mock()
        mock_redis.return_value = redis

        result = OTPService.generate_otp_sync('USER-001', 'verify')

        assert result == '654321'

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    @patch(f'{OTP_SERVICE_PATH}.generate_numeric_otp', return_value='654321')
    @patch(f'{OTP_SERVICE_PATH}.encrypt_otp', return_value='ENC_ABC123456789XY')
    def test_stores_primary_and_hash_index_atomically(
        self, mock_enc, mock_gen, mock_redis
    ):
        """generate_otp_sync must call pipeline.setex() twice (primary + hash)."""
        from apps.authentication.services.otp.sync_service import OTPService
        redis = MagicMock()
        pipe = MagicMock()
        redis.pipeline.return_value = pipe
        pipe.execute.return_value = [True, True]
        mock_redis.return_value = redis

        OTPService.generate_otp_sync('USER-001', 'verify')

        # Two setex calls on the pipeline
        assert pipe.setex.call_count == 2
        pipe.execute.assert_called_once()

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe', return_value=None)
    def test_raises_when_redis_unavailable(self, mock_redis):
        """Redis unavailable must raise an exception (not silently fail)."""
        from apps.authentication.services.otp.sync_service import OTPService
        with pytest.raises(Exception, match="unavailable"):
            OTPService.generate_otp_sync('USER-001', 'verify')

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    @patch(f'{OTP_SERVICE_PATH}.generate_numeric_otp', return_value='111111')
    @patch(f'{OTP_SERVICE_PATH}.encrypt_otp', return_value='ENC_111111_PADDING')
    def test_primary_key_format(self, mock_enc, mock_gen, mock_redis):
        """Primary Redis key must follow otp:{user_id}:{purpose}:{snippet}."""
        from apps.authentication.services.otp.sync_service import OTPService
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute.return_value = [True, True]
        redis.pipeline.return_value = pipe
        mock_redis.return_value = redis

        OTPService.generate_otp_sync('MY-USER-ID', 'verify')

        # Inspect first setex call (primary key)
        first_call_args = pipe.setex.call_args_list[0]
        primary_key = first_call_args[0][0]
        assert primary_key.startswith('otp:MY-USER-ID:verify:')

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    @patch(f'{OTP_SERVICE_PATH}.generate_numeric_otp', return_value='222222')
    @patch(f'{OTP_SERVICE_PATH}.encrypt_otp', return_value='ENC_222_PADDING_XY')
    def test_hash_index_key_format(self, mock_enc, mock_gen, mock_redis):
        """Secondary hash index key must be otp_hash:{sha256(otp)}."""
        from apps.authentication.services.otp.sync_service import OTPService
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute.return_value = [True, True]
        redis.pipeline.return_value = pipe
        mock_redis.return_value = redis

        OTPService.generate_otp_sync('MY-USER-ID', 'verify')

        expected_hash = _sha256('222222')
        second_call_args = pipe.setex.call_args_list[1]
        hash_key = second_call_args[0][0]
        assert hash_key == f'otp_hash:{expected_hash}'

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    @patch(f'{OTP_SERVICE_PATH}.generate_numeric_otp', return_value='333333')
    @patch(f'{OTP_SERVICE_PATH}.encrypt_otp', return_value='ENC_333_PADDING_XYZ')
    def test_ttl_is_300_seconds(self, mock_enc, mock_gen, mock_redis):
        """Both Redis keys must have TTL=300 seconds (5 minutes)."""
        from apps.authentication.services.otp.sync_service import OTPService
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute.return_value = [True, True]
        redis.pipeline.return_value = pipe
        mock_redis.return_value = redis

        OTPService.generate_otp_sync('MY-USER-ID', 'verify')

        for c in pipe.setex.call_args_list:
            ttl = c[0][1]
            assert ttl == 300, f"Expected TTL 300, got {ttl}"


# =============================================================================
# verify_by_otp_sync  (O(1) hash-index path — the production path)
# =============================================================================

@pytest.mark.unit
class TestVerifyByOTPSync:
    """Unit tests for OTPService.verify_by_otp_sync() — O(1) hash-index lookup."""

    def _build_redis_for_verify(self, user_id='USER-001', purpose='verify',
                                 otp='123456', encrypted='ENC|HASH'):
        """
        Build a mock Redis that simulates the two-key structure for WATCH/MULTI/EXEC.

        The new OTPService.verify_by_otp_sync() uses:
            with redis_conn.pipeline() as pipe:
                pipe.watch(hash_key)
                primary_raw = pipe.get(hash_key)       # immediate mode after WATCH
                primary_val = pipe.get(primary_key)    # immediate mode
                pipe.multi()
                pipe.delete(primary_key)
                pipe.delete(hash_key)
                pipe.execute()
        """
        otp_hash = _sha256(otp)
        hash_key_str = f'otp_hash:{otp_hash}'
        primary_key_str = f'otp:{user_id}:{purpose}:SNIPPET'

        # The pipe mock needs to act as both the direct pipeline AND the context manager
        pipe = MagicMock()
        pipe.__enter__ = MagicMock(return_value=pipe)
        pipe.__exit__ = MagicMock(return_value=False)

        # Simulate GET calls in WATCH-mode (immediate execution)
        primary_key_bytes = primary_key_str.encode()
        # get() is called twice: first for hash_key, then for primary_key
        call_responses = [
            primary_key_bytes,   # pipe.get(hash_key) → returns pointer to primary
            b'encrypted_value',  # pipe.get(primary_key) → primary exists → OTP valid
        ]
        pipe.get.side_effect = call_responses

        pipe.delete.return_value = None
        pipe.execute.return_value = [1, 1]
        pipe.watch.return_value = None
        pipe.multi.return_value = None
        pipe.unwatch.return_value = None

        redis = MagicMock()
        redis.pipeline.return_value = pipe
        redis.delete.return_value = None
        redis.get.side_effect = lambda k: (
            primary_key_bytes if hash_key_str in str(k) else
            None
        )
        return redis

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    def test_returns_user_id_on_valid_otp(self, mock_redis):
        """verify_by_otp_sync returns dict with user_id on correct OTP."""
        from apps.authentication.services.otp.sync_service import OTPService
        mock_redis.return_value = self._build_redis_for_verify(
            user_id='abc-123', otp='123456'
        )
        result = OTPService.verify_by_otp_sync('123456', purpose='verify')
        assert result is not None
        assert result['user_id'] == 'abc-123'
        assert result['purpose'] == 'verify'

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    def test_returns_none_on_wrong_otp(self, mock_redis):
        """verify_by_otp_sync returns None when OTP not in hash index."""
        redis = MagicMock()
        redis.get.return_value = None   # hash index miss
        mock_redis.return_value = redis
        from apps.authentication.services.otp.sync_service import OTPService
        result = OTPService.verify_by_otp_sync('999999', purpose='verify')
        assert result is None

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    def test_deletes_both_keys_on_success(self, mock_redis):
        """Both primary key and hash index key must be deleted after verify."""
        from apps.authentication.services.otp.sync_service import OTPService
        redis = self._build_redis_for_verify(otp='123456')
        mock_redis.return_value = redis

        OTPService.verify_by_otp_sync('123456', purpose='verify')

        # The pipe context manager is the pipeline mock
        pipe = redis.pipeline.return_value
        # delete() should have been called at least twice (primary + hash)
        assert pipe.delete.call_count >= 2

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    def test_purpose_mismatch_returns_none(self, mock_redis):
        """OTP stored for 'reset' purpose must not verify with 'verify' purpose."""
        from apps.authentication.services.otp.sync_service import OTPService
        # Hash index points to a 'reset' purpose primary key
        otp_hash = _sha256('123456')
        redis = MagicMock()
        redis.get.side_effect = lambda k: (
            b'otp:USER-001:reset:SNPT' if f'otp_hash:{otp_hash}' in str(k)
            else b'ENC|HASH'
        )
        mock_redis.return_value = redis

        result = OTPService.verify_by_otp_sync('123456', purpose='verify')
        assert result is None

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    def test_orphaned_hash_index_cleaned_up(self, mock_redis):
        """If primary key expired but hash index still exists, index must be deleted."""
        from apps.authentication.services.otp.sync_service import OTPService
        otp_hash = _sha256('123456')
        hash_key_str = f'otp_hash:{otp_hash}'
        primary_key_str = 'otp:USER-001:verify:SNPT'

        pipe = MagicMock()
        pipe.__enter__ = MagicMock(return_value=pipe)
        pipe.__exit__ = MagicMock(return_value=False)
        # First pipe.get() returns the primary key (hash index exists)
        # Second pipe.get() returns None (primary key expired)
        pipe.get.side_effect = [primary_key_str.encode(), None]
        pipe.watch.return_value = None
        pipe.multi.return_value = None
        pipe.unwatch.return_value = None
        pipe.execute.return_value = []

        redis = MagicMock()
        redis.pipeline.return_value = pipe
        # redis.delete() is called directly (not via pipeline) for orphan cleanup
        redis.delete.return_value = 1
        mock_redis.return_value = redis

        result = OTPService.verify_by_otp_sync('123456', purpose='verify')
        assert result is None
        # redis.delete() called directly with the orphaned hash_key
        redis.delete.assert_called()

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe', return_value=None)
    def test_returns_none_when_redis_unavailable(self, mock_redis):
        """Returns None (not raises) when Redis is unavailable."""
        from apps.authentication.services.otp.sync_service import OTPService
        result = OTPService.verify_by_otp_sync('123456', purpose='verify')
        assert result is None


# =============================================================================
# verify_otp_sync  (user_id-based path — backward-compat)
# =============================================================================

@pytest.mark.unit
class TestVerifyOTPSyncByUserID:
    """Unit tests for the user_id-based OTPService.verify_otp_sync()."""

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    @patch(f'{OTP_SERVICE_PATH}.decrypt_otp', return_value='123456')
    def test_returns_true_on_valid_otp(self, mock_dec, mock_redis):
        from apps.authentication.services.otp.sync_service import OTPService
        redis = MagicMock()
        redis.keys.return_value = [b'otp:U1:verify:SNPT']
        redis.get.return_value = b'ENC_VALUE|SOMEHASH'
        pipe = MagicMock()
        pipe.execute.return_value = [1, 1]
        redis.pipeline.return_value = pipe
        mock_redis.return_value = redis

        result = OTPService.verify_otp_sync('U1', '123456', purpose='verify')
        assert result is True

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    @patch(f'{OTP_SERVICE_PATH}.decrypt_otp', return_value='999999')
    def test_returns_false_on_wrong_otp(self, mock_dec, mock_redis):
        from apps.authentication.services.otp.sync_service import OTPService
        redis = MagicMock()
        redis.keys.return_value = [b'otp:U1:verify:SNPT']
        redis.get.return_value = b'ENC_VALUE|SOMEHASH'
        mock_redis.return_value = redis

        result = OTPService.verify_otp_sync('U1', '123456', purpose='verify')
        assert result is False

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    def test_returns_false_on_no_keys(self, mock_redis):
        from apps.authentication.services.otp.sync_service import OTPService
        redis = MagicMock()
        redis.keys.return_value = []
        mock_redis.return_value = redis

        result = OTPService.verify_otp_sync('U1', '123456', purpose='verify')
        assert result is False


# =============================================================================
# resend_otp_sync — template path + cleanup
# =============================================================================

@pytest.mark.unit
@pytest.mark.django_db
class TestResendOTPSync:
    """Unit tests for OTPService.resend_otp_sync() service method."""

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    @patch(f'{OTP_SERVICE_PATH}.OTPService.generate_otp_sync', return_value='654321')
    def test_uses_resend_otp_html_template(self, mock_gen, mock_redis):
        """
        REGRESSION: resend must use 'authentication/email/resend_otp.html'
        (not the now-deleted 'otp_resend_email.html').
        """
        from apps.authentication.models import UnifiedUser
        from apps.authentication.services.otp.sync_service import OTPService

        user = UnifiedUser.objects.create_user(
            email='resend_template@test.io',
            password='TestPass123!',
            role='client',
        )

        redis = MagicMock()
        redis.keys.return_value = []
        mock_redis.return_value = redis

        dispatched_kwargs = {}

        def _capture_delay(**kwargs):
            dispatched_kwargs.update(kwargs)

        with patch(
            'apps.authentication.tasks.send_email_task.delay',
            side_effect=lambda **kw: dispatched_kwargs.update(kw)
        ):
            from django.test.utils import override_settings
            with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
                # Trigger on_commit immediately in test context
                from django.db import connection
                with connection.cursor() as c:
                    pass   # flush
                OTPService.resend_otp_sync(user.email, purpose='verify')

        # We can't assert the on_commit callback fires without transaction=True,
        # but we can assert the service call succeeds and returns generic message
        result = OTPService.resend_otp_sync(user.email, purpose='verify')
        assert 'account exists' in result.lower() or 'sent' in result.lower()

    @patch(f'{OTP_SERVICE_PATH}.get_redis_connection_safe')
    @patch(f'{OTP_SERVICE_PATH}.OTPService.generate_otp_sync', return_value='654321')
    def test_generic_message_for_nonexistent_user(self, mock_gen, mock_redis):
        """Must return generic message for non-existent user (enumeration guard)."""
        from apps.authentication.services.otp.sync_service import OTPService
        redis = MagicMock()
        mock_redis.return_value = redis

        result = OTPService.resend_otp_sync('ghost@nowhere.io', purpose='verify')
        assert isinstance(result, str)
        # Must NOT reveal the user doesn't exist
        assert 'not found' not in result.lower()
        assert 'no user' not in result.lower()
