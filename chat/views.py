# chat/views.py

from rest_framework import generics
from chat.models import Message
from chat.serializers import MessageSerializer

class MessageListView(generics.ListAPIView):
    serializer_class = MessageSerializer

    def get_queryset(self):
        try:
            sender = self.request.user
            recipient_id = self.kwargs['recipient_id']
            return Message.objects.filter(sender=sender, recipient_id=recipient_id) | \
                   Message.objects.filter(sender_id=recipient_id, recipient=sender)
        except Exception as e:
            print(f"Error retrieving messages: {e}")
            return Message.objects.none()

class MessageCreateView(generics.CreateAPIView):
    serializer_class = MessageSerializer

    def perform_create(self, serializer):
        try:
            serializer.save(sender=self.request.user)
        except Exception as e:
            print(f"Error creating message: {e}")
            raise e
