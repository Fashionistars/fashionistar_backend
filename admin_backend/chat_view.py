# admin_backend/views.py

from rest_framework import generics
from rest_framework.permissions import IsAdminUser
from chat.models import Message
from admin_backend.serializers import MessageViewSerializer

class AdminMessageDetailView(generics.RetrieveAPIView):
    queryset = Message.objects.all()
    serializer_class = MessageViewSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        try:
            return super().get_object()
        except Exception as e:
            print(f"Error retrieving message: {e}")
            raise

class AdminMessageListView(generics.ListAPIView):
    queryset = Message.objects.all()
    serializer_class = MessageViewSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        try:
            return super().get_queryset()
        except Exception as e:
            print(f"Error retrieving messages: {e}")
            return Message.objects.none()
