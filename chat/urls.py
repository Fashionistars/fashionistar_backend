# chat/urls.py

from django.urls import path
from .views import MessageListView, MessageCreateView

urlpatterns = [
    path('chat/messages/<int:recipient_id>/', MessageListView.as_view(), name='message-list'),
    path('chat/create-message/', MessageCreateView.as_view(), name='message-create'),
]
