"""
apps/chat/apis/sync/chat_views.py
DRF API views for the Chat messaging domain.

NOTE: success_response() and error_response() already return DRF Response objects.
      Do NOT wrap them in Response() again.

Permission matrix:
  • ConversationListView:   IsAuthenticated (buyer or vendor — own threads)
  • StartConversationView:  IsAuthenticated (buyer only)
  • ConversationDetailView: IsAuthenticated (conversation participant only)
  • SendMessageView:        IsAuthenticated (conversation participant)
  • CreateOfferView:        IsAuthenticated (vendor of conversation only)
  • RespondOfferView:       IsAuthenticated (buyer of conversation only)
  • FlagConversationView:   IsAuthenticated (conversation participant)
"""
import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.renderers import success_response, error_response
from apps.chat.models import Conversation, ChatOffer
from apps.chat.selectors.chat_selectors import (
    get_user_conversations,
    get_conversation_messages,
)
from apps.chat.serializers.chat_serializers import (
    ConversationListSerializer,
    MessageSerializer,
    SendMessageSerializer,
    StartConversationSerializer,
    CreateOfferSerializer,
    ChatOfferSerializer,
    FlagConversationSerializer,
)
from apps.chat.services import chat_service

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION
# ─────────────────────────────────────────────────────────────────────────────

class ConversationListView(APIView):
    """
    GET /api/v1/chat/conversations/
    Returns all conversations for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = get_user_conversations(request.user)
        serializer = ConversationListSerializer(
            qs, many=True, context={"request": request}
        )
        return success_response(
            data=serializer.data,
            message="Conversations fetched successfully.",
        )


class StartConversationView(APIView):
    """
    POST /api/v1/chat/conversations/start/
    Buyer starts a new conversation with a vendor.
    Idempotent — returns existing active thread if one exists.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = StartConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from apps.authentication.models import UnifiedUser
        vendor = get_object_or_404(UnifiedUser, id=data["vendor_id"])

        try:
            conversation, created = chat_service.get_or_create_conversation(
                buyer=request.user,
                vendor=vendor,
                product_id=data.get("product_id"),
                product_title_snapshot=data.get("product_title_snapshot", ""),
            )
        except ValueError as exc:
            return error_response(str(exc), status=status.HTTP_400_BAD_REQUEST)

        # Send initial message if provided
        if data.get("initial_message"):
            try:
                chat_service.send_message(
                    conversation=conversation,
                    author=request.user,
                    body=data["initial_message"],
                )
            except Exception as exc:
                logger.warning("Initial message failed: %s", exc)

        out = ConversationListSerializer(
            conversation, context={"request": request}
        )
        return success_response(
            data=out.data,
            message="Conversation created." if created else "Existing conversation returned.",
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ConversationDetailView(APIView):
    """
    GET /api/v1/chat/conversations/<conversation_id>/
    GET messages for a conversation (paginated, newest-first).
    Also marks all messages as read for the requesting participant.
    """
    permission_classes = [IsAuthenticated]

    def _get_conversation_or_403(self, conversation_id, user):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if user.id not in (conversation.buyer_id, conversation.vendor_id):
            return None, error_response(
                "You are not a participant in this conversation.",
                status=status.HTTP_403_FORBIDDEN,
            )
        return conversation, None

    def get(self, request: Request, conversation_id: str) -> Response:
        conversation, err = self._get_conversation_or_403(conversation_id, request.user)
        if err:
            return err

        before_id = request.query_params.get("before_id")
        messages_qs = get_conversation_messages(
            conversation, page_size=50, before_id=before_id
        )
        serializer = MessageSerializer(messages_qs, many=True)

        # Mark as read (best effort)
        try:
            chat_service.mark_messages_read(conversation, request.user)
        except Exception as exc:
            logger.warning("Mark-read failed: %s", exc)

        return success_response(
            data={"messages": serializer.data},
            message="Messages fetched.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# SEND MESSAGE
# ─────────────────────────────────────────────────────────────────────────────

class SendMessageView(APIView):
    """
    POST /api/v1/chat/conversations/<conversation_id>/messages/
    Send a text message in a conversation.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, conversation_id: str) -> Response:
        conversation = get_object_or_404(Conversation, id=conversation_id)

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            message = chat_service.send_message(
                conversation=conversation,
                author=request.user,
                body=serializer.validated_data["body"],
                message_type=serializer.validated_data["message_type"],
            )
        except (PermissionError, ValueError) as exc:
            return error_response(str(exc), status=status.HTTP_400_BAD_REQUEST)

        return success_response(
            data=MessageSerializer(message).data,
            message="Message sent.",
            status=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# OFFER
# ─────────────────────────────────────────────────────────────────────────────

class CreateOfferView(APIView):
    """
    POST /api/v1/chat/conversations/<conversation_id>/offers/
    Vendor creates a price offer for the buyer.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, conversation_id: str) -> Response:
        conversation = get_object_or_404(Conversation, id=conversation_id)

        serializer = CreateOfferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            offer = chat_service.create_chat_offer(
                conversation=conversation,
                vendor=request.user,
                product_id=data["product_id"],
                product_title_snapshot=data["product_title_snapshot"],
                offered_price=str(data["offered_price"]),
                quantity=data["quantity"],
                notes=data.get("notes", ""),
            )
        except (PermissionError, ValueError) as exc:
            return error_response(str(exc), status=status.HTTP_400_BAD_REQUEST)

        return success_response(
            data=ChatOfferSerializer(offer).data,
            message="Offer created.",
            status=status.HTTP_201_CREATED,
        )


class RespondOfferView(APIView):
    """
    POST /api/v1/chat/offers/<offer_id>/accept/
    POST /api/v1/chat/offers/<offer_id>/decline/
    Buyer accepts or declines an offer.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, offer_id: str, action: str) -> Response:
        offer = get_object_or_404(ChatOffer, id=offer_id)

        try:
            if action == "accept":
                offer = chat_service.accept_offer(offer, request.user)
            elif action == "decline":
                offer = chat_service.decline_offer(offer, request.user)
            else:
                return error_response(
                    f"Unknown action: {action}",
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except (PermissionError, ValueError) as exc:
            return error_response(str(exc), status=status.HTTP_400_BAD_REQUEST)

        return success_response(
            data=ChatOfferSerializer(offer).data,
            message=f"Offer {action}d successfully.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# MODERATION
# ─────────────────────────────────────────────────────────────────────────────

class FlagConversationView(APIView):
    """
    POST /api/v1/chat/conversations/<conversation_id>/flag/
    File a moderation report for a conversation.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, conversation_id: str) -> Response:
        conversation = get_object_or_404(Conversation, id=conversation_id)

        serializer = FlagConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            flag = chat_service.flag_conversation(
                conversation=conversation,
                reported_by=request.user,
                reason=serializer.validated_data["reason"],
                details=serializer.validated_data.get("details", ""),
            )
        except PermissionError as exc:
            return error_response(str(exc), status=status.HTTP_403_FORBIDDEN)

        return success_response(
            data={"flag_id": str(flag.id)},
            message="Conversation reported. Our moderation team will review it.",
            status=status.HTTP_201_CREATED,
        )
