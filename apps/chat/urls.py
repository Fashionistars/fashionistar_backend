"""
apps/chat/urls.py — Chat domain URL routing.
"""
from django.urls import path
from apps.chat.apis.sync.chat_views import (
    ConversationListView,
    StartConversationView,
    ConversationDetailView,
    SendMessageView,
    MarkConversationReadView,
    CreateOfferView,
    RespondOfferView,
    FlagConversationView,
)

app_name = "chat"

urlpatterns = [
    # ── Conversations ──────────────────────────────────────────────────────
    # GET  /api/v1/chat/conversations/          list user's conversations
    # POST /api/v1/chat/conversations/          start or retrieve a conversation
    path("conversations/", ConversationListView.as_view(), name="conversation-list"),
    path("conversations/start/", StartConversationView.as_view(), name="conversation-start"),

    # ── Conversation Detail + Messages ─────────────────────────────────────
    # GET  /api/v1/chat/conversations/<id>/         get messages (paginated)
    path(
        "conversations/<uuid:conversation_id>/",
        ConversationDetailView.as_view(),
        name="conversation-detail",
    ),
    # POST /api/v1/chat/conversations/<id>/messages/  send a message
    path(
        "conversations/<uuid:conversation_id>/messages/",
        SendMessageView.as_view(),
        name="send-message",
    ),
    path(
        "conversations/<uuid:conversation_id>/read/",
        MarkConversationReadView.as_view(),
        name="mark-conversation-read",
    ),

    # ── Offers ────────────────────────────────────────────────────────────
    # POST /api/v1/chat/conversations/<id>/offers/     vendor creates offer
    path(
        "conversations/<uuid:conversation_id>/offers/",
        CreateOfferView.as_view(),
        name="create-offer",
    ),
    # POST /api/v1/chat/offers/<id>/accept/   buyer accepts
    # POST /api/v1/chat/offers/<id>/decline/  buyer declines
    path(
        "offers/<uuid:offer_id>/<str:action>/",
        RespondOfferView.as_view(),
        name="respond-offer",
    ),

    # ── Moderation ────────────────────────────────────────────────────────
    # POST /api/v1/chat/conversations/<id>/flag/
    path(
        "conversations/<uuid:conversation_id>/flag/",
        FlagConversationView.as_view(),
        name="flag-conversation",
    ),
]
