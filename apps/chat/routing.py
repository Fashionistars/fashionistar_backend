"""
WebSocket routes for the modular chat domain.
"""

from django.urls import path

from apps.chat.consumers import ChatConversationConsumer

websocket_urlpatterns = [
    path(
        "ws/chat/<uuid:conversation_id>/",
        ChatConversationConsumer.as_asgi(),
        name="ws-chat-conversation",
    ),
]
