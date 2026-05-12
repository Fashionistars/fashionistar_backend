"""
apps/chat/tests/test_chat_api.py

Enterprise test suite for the Chat domain.

Coverage:
  1. Conversation creation (idempotency, self-chat prevention)
  2. Message sending (permission matrix, writable state enforcement)
  3. Mark-read counters
  4. Offer lifecycle (create, accept, decline, double-accept prevention)
  5. Moderation flag + auto-escalation
  6. API endpoint authorization matrix
"""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.urls import reverse

from apps.authentication.models import UnifiedUser
from apps.chat.models import (
    Conversation,
    ConversationStatus,
    Message,
    ChatOffer,
    OfferStatus,
    ModerationFlag,
    ChatEscalation,
    EscalationStatus,
)
from apps.chat.services.chat_service import (
    get_or_create_conversation,
    send_message,
    mark_messages_read,
    create_chat_offer,
    accept_offer,
    decline_offer,
    flag_conversation,
)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def buyer(db):
    u = UnifiedUser.objects.create_user(
        email="buyer_chat@test.com",
        password="TestPass123!",
    )
    u.is_active = True
    u.save(update_fields=["is_active"])
    return u


@pytest.fixture
def vendor(db):
    u = UnifiedUser.objects.create_user(
        email="vendor_chat@test.com",
        password="TestPass123!",
    )
    u.is_active = True
    u.save(update_fields=["is_active"])
    return u


@pytest.fixture
def other_user(db):
    u = UnifiedUser.objects.create_user(
        email="outsider@test.com",
        password="TestPass123!",
    )
    u.is_active = True
    u.save(update_fields=["is_active"])
    return u


@pytest.fixture
def conversation(db, buyer, vendor):
    return Conversation.objects.create(
        buyer=buyer,
        vendor=vendor,
        product_id=None,
        status=ConversationStatus.ACTIVE,
    )


@pytest.fixture
def message(db, conversation, buyer):
    return Message.objects.create(
        conversation=conversation,
        author=buyer,
        body="Hello from buyer!",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONVERSATION CREATION
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationCreation:

    @patch("apps.chat.services.chat_service.create_notification")
    def test_creates_new_conversation(self, mock_notify, db, buyer, vendor):
        conv, created = get_or_create_conversation(buyer=buyer, vendor=vendor)
        assert created is True
        assert conv.buyer == buyer
        assert conv.vendor == vendor
        assert conv.status == ConversationStatus.ACTIVE

    @patch("apps.chat.services.chat_service.create_notification")
    def test_idempotent_second_call_returns_existing(self, mock_notify, db, buyer, vendor):
        conv1, created1 = get_or_create_conversation(buyer=buyer, vendor=vendor)
        conv2, created2 = get_or_create_conversation(buyer=buyer, vendor=vendor)
        assert conv1.id == conv2.id
        assert created2 is False

    def test_self_chat_raises_value_error(self, db, buyer):
        with pytest.raises(ValueError, match="themselves"):
            get_or_create_conversation(buyer=buyer, vendor=buyer)

    @patch("apps.chat.services.chat_service.create_notification")
    def test_different_products_create_separate_conversations(self, mock_notify, db, buyer, vendor):
        import uuid
        p1 = uuid.uuid4()
        p2 = uuid.uuid4()
        conv1, _ = get_or_create_conversation(buyer=buyer, vendor=vendor, product_id=p1)
        conv2, _ = get_or_create_conversation(buyer=buyer, vendor=vendor, product_id=p2)
        assert conv1.id != conv2.id


# ─────────────────────────────────────────────────────────────────────────────
# 2. MESSAGE SENDING
# ─────────────────────────────────────────────────────────────────────────────

class TestMessageSending:

    def test_buyer_can_send_message(self, db, conversation, buyer):
        msg = send_message(conversation=conversation, author=buyer, body="Hello vendor!")
        assert msg.body == "Hello vendor!"
        assert msg.author == buyer
        assert msg.is_read_by_buyer is True
        assert msg.is_read_by_vendor is False

    def test_vendor_can_send_message(self, db, conversation, vendor):
        msg = send_message(conversation=conversation, author=vendor, body="Hello buyer!")
        assert msg.is_read_by_vendor is True
        assert msg.is_read_by_buyer is False

    def test_outsider_cannot_send_message(self, db, conversation, other_user):
        with pytest.raises(PermissionError):
            send_message(conversation=conversation, author=other_user, body="Intruder!")

    def test_archived_conversation_rejects_messages(self, db, conversation, buyer):
        conversation.status = ConversationStatus.ARCHIVED
        conversation.save()
        with pytest.raises(ValueError, match="archived"):
            send_message(conversation=conversation, author=buyer, body="Should fail")

    def test_blocked_conversation_rejects_messages(self, db, conversation, buyer):
        conversation.status = ConversationStatus.BLOCKED
        conversation.save()
        with pytest.raises(ValueError, match="blocked"):
            send_message(conversation=conversation, author=buyer, body="Should fail")

    def test_last_message_at_updated(self, db, conversation, buyer):
        assert conversation.last_message_at is None
        send_message(conversation=conversation, author=buyer, body="Hi")
        conversation.refresh_from_db()
        assert conversation.last_message_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# 3. MARK READ
# ─────────────────────────────────────────────────────────────────────────────

class TestMarkRead:

    def test_buyer_marks_vendor_messages_read(self, db, conversation, buyer, vendor):
        # Vendor sends 3 messages
        for i in range(3):
            Message.objects.create(
                conversation=conversation,
                author=vendor,
                body=f"Vendor msg {i}",
                is_read_by_buyer=False,
                is_read_by_vendor=True,
            )
        Conversation.objects.filter(id=conversation.id).update(unread_buyer_count=3)
        count = mark_messages_read(conversation, buyer)
        assert count == 3
        conversation.refresh_from_db()
        assert conversation.unread_buyer_count == 0

    def test_outsider_cannot_mark_read(self, db, conversation, other_user):
        with pytest.raises(PermissionError):
            mark_messages_read(conversation, other_user)


# ─────────────────────────────────────────────────────────────────────────────
# 4. CHAT OFFER LIFECYCLE
# ─────────────────────────────────────────────────────────────────────────────

class TestChatOfferLifecycle:
    import uuid as _uuid
    PRODUCT_ID = _uuid.uuid4()

    @patch("apps.chat.services.chat_service.create_notification")
    def test_vendor_can_create_offer(self, mock_notify, db, conversation, vendor):
        offer = create_chat_offer(
            conversation=conversation,
            vendor=vendor,
            product_id=self.PRODUCT_ID,
            product_title_snapshot="Test Dress",
            offered_price="25000.00",
            quantity=1,
        )
        assert offer.status == OfferStatus.PENDING
        assert str(offer.offered_price) == "25000.00"

    def test_buyer_cannot_create_offer(self, db, conversation, buyer):
        with pytest.raises(PermissionError):
            create_chat_offer(
                conversation=conversation,
                vendor=buyer,  # buyer, not vendor
                product_id=self.PRODUCT_ID,
                product_title_snapshot="Test",
                offered_price="1000.00",
            )

    @patch("apps.chat.services.chat_service.create_notification")
    def test_buyer_accepts_offer(self, mock_notify, db, conversation, vendor, buyer):
        offer = create_chat_offer(
            conversation=conversation,
            vendor=vendor,
            product_id=self.PRODUCT_ID,
            product_title_snapshot="Dress",
            offered_price="5000.00",
        )
        accepted = accept_offer(offer, buyer)
        assert accepted.status == OfferStatus.ACCEPTED
        assert accepted.responded_at is not None

    @patch("apps.chat.services.chat_service.create_notification")
    def test_buyer_declines_offer(self, mock_notify, db, conversation, vendor, buyer):
        offer = create_chat_offer(
            conversation=conversation,
            vendor=vendor,
            product_id=self.PRODUCT_ID,
            product_title_snapshot="Dress",
            offered_price="5000.00",
        )
        declined = decline_offer(offer, buyer)
        assert declined.status == OfferStatus.DECLINED

    @patch("apps.chat.services.chat_service.create_notification")
    def test_double_accept_raises_value_error(self, mock_notify, db, conversation, vendor, buyer):
        offer = create_chat_offer(
            conversation=conversation,
            vendor=vendor,
            product_id=self.PRODUCT_ID,
            product_title_snapshot="Dress",
            offered_price="5000.00",
        )
        accept_offer(offer, buyer)
        with pytest.raises(ValueError):
            accept_offer(offer, buyer)  # already accepted

    @patch("apps.chat.services.chat_service.create_notification")
    def test_vendor_cannot_accept_own_offer(self, mock_notify, db, conversation, vendor):
        offer = create_chat_offer(
            conversation=conversation,
            vendor=vendor,
            product_id=self.PRODUCT_ID,
            product_title_snapshot="Dress",
            offered_price="5000.00",
        )
        with pytest.raises(PermissionError):
            accept_offer(offer, vendor)  # vendor is not the buyer


# ─────────────────────────────────────────────────────────────────────────────
# 5. MODERATION FLAG + AUTO-ESCALATION
# ─────────────────────────────────────────────────────────────────────────────

class TestModerationAndEscalation:

    def test_buyer_can_flag_conversation(self, db, conversation, buyer):
        flag = flag_conversation(
            conversation=conversation,
            reported_by=buyer,
            reason="harassment",
            details="Vendor threatening me.",
        )
        assert flag.reason == "harassment"
        assert flag.is_reviewed is False

    def test_flag_auto_escalates_conversation(self, db, conversation, buyer):
        flag_conversation(conversation=conversation, reported_by=buyer, reason="spam")
        conversation.refresh_from_db()
        assert conversation.status == ConversationStatus.ESCALATED

    def test_flag_creates_escalation_record(self, db, conversation, buyer):
        flag_conversation(conversation=conversation, reported_by=buyer, reason="fraud")
        assert ChatEscalation.objects.filter(conversation=conversation).exists()

    def test_flag_idempotent_escalation(self, db, conversation, buyer):
        # Filing 2 flags should not create 2 escalation records
        flag_conversation(conversation=conversation, reported_by=buyer, reason="spam")
        flag_conversation(conversation=conversation, reported_by=buyer, reason="fraud")
        assert ChatEscalation.objects.filter(conversation=conversation).count() == 1

    def test_outsider_cannot_flag(self, db, conversation, other_user):
        with pytest.raises(PermissionError):
            flag_conversation(conversation=conversation, reported_by=other_user, reason="spam")


# ─────────────────────────────────────────────────────────────────────────────
# 6. API AUTHORIZATION MATRIX (endpoint-level)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestChatAPIAuthorization:

    def test_unauthenticated_user_cannot_list_conversations(self, client):
        url = "/api/v1/chat/conversations/"
        response = client.get(url)
        assert response.status_code == 401

    def test_unauthenticated_user_cannot_start_conversation(self, client):
        url = "/api/v1/chat/conversations/start/"
        response = client.post(url, {}, content_type="application/json")
        assert response.status_code == 401

    def test_authenticated_buyer_can_list_conversations(self, client, buyer):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(buyer)
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {refresh.access_token}"
        url = "/api/v1/chat/conversations/"
        response = client.get(url)
        assert response.status_code == 200

    def test_authenticated_user_can_start_conversation(self, client, buyer, vendor):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(buyer)
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {refresh.access_token}"
        url = "/api/v1/chat/conversations/start/"
        response = client.post(
            url,
            {"vendor_id": str(vendor.id), "initial_message": "Hello!"},
            content_type="application/json",
        )
        assert response.status_code in (200, 201)

    def test_non_participant_cannot_view_conversation(self, client, conversation, other_user):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(other_user)
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {refresh.access_token}"
        url = f"/api/v1/chat/conversations/{conversation.id}/"
        response = client.get(url)
        assert response.status_code == 403
