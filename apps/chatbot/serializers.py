"""
Chatbot Serializers for Fashionistar.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ChatbotSession, Conversation, Message, ChatbotResponse

User = get_user_model()


class UserBasicSerializer(serializers.ModelSerializer):
    """
    Serializer for basic user information.
    """
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'phone']
        read_only_fields = ['id', 'phone']


class ChatbotSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for chatbot sessions.
    """
    user = UserBasicSerializer(read_only=True)
    duration = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()
    conversation_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatbotSession
        fields = [
            'id', 'user', 'session_type', 'status', 'context_data',
            'started_at', 'last_activity', 'ended_at', 'expires_at',
            'duration', 'is_active', 'conversation_count', 'metadata'
        ]
        read_only_fields = [
            'id', 'user', 'started_at', 'last_activity', 'duration', 'is_active'
        ]
    
    def get_conversation_count(self, obj):
        return obj.conversations.count()


class MessageSerializer(serializers.ModelSerializer):
    """
    Serializer for messages.
    """
    is_from_user = serializers.ReadOnlyField()
    is_from_bot = serializers.ReadOnlyField()
    
    class Meta:
        model = Message
        fields = [
            'id', 'sender_type', 'message_type', 'content', 'response_data',
            'ai_confidence', 'processing_time', 'is_sensitive',
            'created_at', 'edited_at', 'is_from_user', 'is_from_bot', 'metadata'
        ]
        read_only_fields = [
            'id', 'created_at', 'edited_at', 'is_from_user', 'is_from_bot'
        ]
    
    def validate_content(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Message content cannot be empty.")
        
        if len(value) > 4000:
            raise serializers.ValidationError("Message content cannot exceed 4000 characters.")
        
        return value.strip()


class ConversationSerializer(serializers.ModelSerializer):
    """
    Serializer for conversations including message history.
    """
    session = ChatbotSessionSerializer(read_only=True)
    messages = MessageSerializer(many=True, read_only=True)
    message_count = serializers.ReadOnlyField()
    last_message_time = serializers.ReadOnlyField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'session', 'conversation_type', 'title', 'is_active',
            'started_at', 'updated_at', 'summary', 'tags', 'messages',
            'message_count', 'last_message_time', 'metadata'
        ]
        read_only_fields = [
            'id', 'session', 'started_at', 'updated_at', 'message_count', 'last_message_time'
        ]


class ConversationListSerializer(serializers.ModelSerializer):
    """
    Serializer for conversation list (excluding messages).
    """
    message_count = serializers.ReadOnlyField()
    last_message_time = serializers.ReadOnlyField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'conversation_type', 'title', 'is_active',
            'started_at', 'updated_at', 'message_count', 'last_message_time'
        ]


class ChatbotResponseSerializer(serializers.ModelSerializer):
    """
    Serializer for chatbot responses.
    """
    class Meta:
        model = ChatbotResponse
        fields = [
            'id', 'category', 'target_user', 'trigger_keywords',
            'response_text', 'response_data', 'is_active', 'priority',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# Request / Response Serializers


class SendMessageRequestSerializer(serializers.Serializer):
    """
    Serializer to validate sending a message.
    """
    message = serializers.CharField(
        max_length=4000,
        help_text="User message content"
    )
    message_type = serializers.ChoiceField(
        choices=Message.MESSAGE_TYPES,
        default='text',
        help_text="Message type"
    )
    context = serializers.JSONField(
        required=False,
        help_text="Additional context for message processing"
    )
    
    def validate_message(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Message cannot be empty.")
        return value.strip()


class ChatbotResponseDataSerializer(serializers.Serializer):
    """
    Serializer for formatted chatbot responses.
    """
    content = serializers.CharField(help_text="Response content")
    message_type = serializers.CharField(help_text="Message type")
    response_data = serializers.JSONField(
        required=False,
        help_text="Structured response data"
    )
    ai_confidence = serializers.FloatField(
        required=False,
        help_text="AI confidence score"
    )
    processing_time = serializers.FloatField(
        required=False,
        help_text="Processing time in seconds"
    )
    quick_replies = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="Suggested quick replies"
    )


class SendMessageResponseSerializer(serializers.Serializer):
    """
    Serializer for the response of sending a message.
    """
    response = ChatbotResponseDataSerializer(help_text="Chatbot response")
    user_message_id = serializers.UUIDField(help_text="User message UUID")
    bot_message_id = serializers.UUIDField(help_text="Bot message UUID")
    conversation_id = serializers.UUIDField(help_text="Conversation UUID")
    session_id = serializers.UUIDField(help_text="Session UUID")


class StartSessionResponseSerializer(serializers.Serializer):
    """
    Serializer for starting a chatbot session.
    """
    session = ChatbotSessionSerializer(help_text="Session info")
    greeting_message = ChatbotResponseDataSerializer(
        required=False,
        help_text="Greeting message"
    )
    quick_replies = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="Initial quick replies"
    )


class StyleAssessmentRequestSerializer(serializers.Serializer):
    """
    Serializer for style and aesthetic assessment.
    """
    preferred_style = serializers.CharField(help_text="Primary style or aesthetic preference")
    budget_range = serializers.CharField(help_text="Estimated budget range")
    formality_level = serializers.IntegerField(
        min_value=1,
        max_value=10,
        help_text="Formality level (1-10)"
    )
    size_preferences = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Preferred sizing guidelines"
    )
    sizing_notes = serializers.CharField(
        required=False,
        help_text="Specific details regarding styling/fit history"
    )


class SizeRecommendationRequestSerializer(serializers.Serializer):
    """
    Serializer for sizing and fit recommendation requests.
    """
    measurements = serializers.ListField(
        child=serializers.CharField(),
        help_text="List of body measurements"
    )
    height_cm = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=250,
        help_text="Client height in cm"
    )
    gender = serializers.ChoiceField(
        choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')],
        required=False,
        help_text="Client gender"
    )
    fit_preference = serializers.CharField(
        required=False,
        help_text="Preferred fit profile (e.g. slim, regular, loose)"
    )
    prior_purchases = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Known comfortable sizing in other brands"
    )


class ProductInquiryRequestSerializer(serializers.Serializer):
    """
    Serializer for specific product inquiries.
    """
    product_sku = serializers.CharField(help_text="Product SKU or Identifier")
    client_size = serializers.CharField(
        required=False,
        help_text="Preferred size"
    )
    client_height = serializers.FloatField(
        required=False,
        help_text="Client height (cm)"
    )
    fabric_preferences = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Preferred materials or material warnings (e.g. wool allergy)"
    )
    similar_products = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Similar SKUs of interest"
    )


class BespokeConsultationRequestSerializer(serializers.Serializer):
    """
    Serializer for booking bespoke tailoring consultation.
    """
    tailoring_type = serializers.CharField(
        required=False,
        help_text="Required bespoke item type (e.g. suit, gown, coat)"
    )
    preferred_date = serializers.DateField(
        required=False,
        help_text="Preferred date"
    )
    preferred_time = serializers.CharField(
        required=False,
        help_text="Preferred time slot"
    )
    urgency = serializers.ChoiceField(
        choices=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('rush', 'Rush')
        ],
        default='medium',
        help_text="Urgency level"
    )
    design_details = serializers.CharField(
        required=False,
        help_text="Details of design ideas or reference requests"
    )


class ConversationHistorySerializer(serializers.Serializer):
    """
    Serializer for conversation message history.
    """
    conversation = ConversationListSerializer(help_text="Conversation summary")
    messages = MessageSerializer(many=True, help_text="Messages list")
    total_messages = serializers.IntegerField(help_text="Total messages count")
    has_more = serializers.BooleanField(
        help_text="Whether more messages are available"
    )