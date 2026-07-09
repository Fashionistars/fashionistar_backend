"""
Chatbot System Models for Fashionistar.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinLengthValidator
import uuid

User = get_user_model()


class ChatbotSession(models.Model):
    """
    Chatbot session to track conversation context per user.
    """
    
    SESSION_TYPES = [
        ('client', 'Client'),
        ('vendor', 'Vendor'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chatbot_sessions',
        verbose_name='User'
    )
    
    session_type = models.CharField(
        max_length=10,
        choices=SESSION_TYPES,
        verbose_name='Session Type'
    )
    
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='Status'
    )
    
    context_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Context Data',
        help_text='Contextual info to maintain conversation state'
    )
    
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Started At'
    )
    
    last_activity = models.DateTimeField(
        auto_now=True,
        verbose_name='Last Activity'
    )
    
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Ended At'
    )
    
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Expires At'
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadata'
    )
    
    class Meta:
        verbose_name = 'Chatbot Session'
        verbose_name_plural = 'Chatbot Sessions'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['session_type', 'status']),
            models.Index(fields=['started_at']),
            models.Index(fields=['last_activity']),
        ]
    
    def __str__(self):
        return f"Session {self.session_type} - {self.user} ({self.status})"
    
    @property
    def is_session_active(self):
        """Check if session is currently active and not expired."""
        return self.status == 'active' and (
            not self.expires_at or timezone.now() < self.expires_at
        )
    
    @property
    def duration(self):
        """Get session duration."""
        if self.ended_at:
            return self.ended_at - self.started_at
        return timezone.now() - self.started_at
    
    def end_session(self):
        """End session, marking it completed."""
        self.status = 'completed'
        self.ended_at = timezone.now()
        self.save(update_fields=['status', 'ended_at'])
    
    # ============================================================================
    # ASYNC METHODS (Django 6.0 native async ORM)
    # ============================================================================
    
    @classmethod
    async def aget_active_session(cls, user):
        """Get active session for a user (async)."""
        return await cls.objects.filter(user=user, status='active').select_related('user').afirst()
    
    @classmethod
    async def aget_session_by_id(cls, session_id):
        """Get session by ID (async)."""
        try:
            return await cls.objects.select_related('user').aget(id=session_id)
        except cls.DoesNotExist:
            return None
    
    async def aget_conversation_count(self):
        """Get total conversation count for this session (async)."""
        return await self.conversations.acount()
    
    async def aget_active_conversation(self):
        """Get active conversation for this session (async)."""
        try:
            return await self.conversations.filter(is_active=True).afirst()
        except Conversation.DoesNotExist:
            return None
    
    async def aget_conversations(self, is_active: bool = None):
        """Get all conversations for this session (async)."""
        queryset = self.conversations.all()
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return [c async for c in queryset.order_by('-started_at')]
    
    async def aend_session(self):
        """End session, marking it completed (async)."""
        self.status = 'completed'
        self.ended_at = timezone.now()
        await self.asave(update_fields=['status', 'ended_at'])


class Conversation(models.Model):
    """
    A specific conversation flow or topic inside a chatbot session.
    """
    
    CONVERSATION_TYPES = [
        ('style_advice', 'Style Advice'),
        ('size_recommendation', 'Size Recommendation'),
        ('product_search', 'Product Search'),
        ('order_inquiry', 'Order Inquiry'),
        ('general_support', 'General Support'),
        ('general', 'General'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    session = models.ForeignKey(
        ChatbotSession,
        on_delete=models.CASCADE,
        related_name='conversations',
        verbose_name='Session'
    )
    
    conversation_type = models.CharField(
        max_length=25,
        choices=CONVERSATION_TYPES,
        default='general',
        verbose_name='Conversation Type'
    )
    
    title = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Title'
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name='Is Active'
    )
    
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Started At'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Updated At'
    )
    
    summary = models.TextField(
        blank=True,
        verbose_name='Summary'
    )
    
    tags = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Tags'
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadata'
    )
    
    class Meta:
        verbose_name = 'Conversation'
        verbose_name_plural = 'Conversations'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['session', 'is_active']),
            models.Index(fields=['conversation_type']),
            models.Index(fields=['started_at']),
        ]
    
    def __str__(self):
        title = self.title or f"Conversation {self.conversation_type}"
        return f"{title} - {self.session.user}"
    
    @property
    def message_count(self):
        """Count total messages in conversation."""
        return self.messages.count()
    
    @property
    def last_message_time(self):
        """Get timestamp of last message."""
        last_message = self.messages.order_by('-created_at').first()
        return last_message.created_at if last_message else self.started_at
    
    # ============================================================================
    # ASYNC METHODS (Django 6.0 native async ORM)
    # ============================================================================
    
    async def aget_message_count(self):
        """Get total message count for this conversation (async)."""
        return await self.messages.acount()
    
    async def aget_last_message(self):
        """Get last message in this conversation (async)."""
        return await self.messages.order_by('-created_at').afirst()
    
    async def aget_messages(self, limit: int = 10):
        """Get recent messages for this conversation (async)."""
        return [m async for m in self.messages.order_by('-created_at')[:limit]]
    
    async def aget_messages_by_sender(self, sender_type: str, limit: int = 10):
        """Get messages by sender type for this conversation (async)."""
        queryset = self.messages.filter(sender_type=sender_type)
        return [m async for m in queryset.order_by('-created_at')[:limit]]


class Message(models.Model):
    """
    Message inside a chatbot conversation.
    """
    
    SENDER_TYPES = [
        ('user', 'User'),
        ('bot', 'Bot'),
        ('system', 'System'),
    ]
    
    MESSAGE_TYPES = [
        ('text', 'Text'),
        ('quick_reply', 'Quick Reply'),
        ('attachment', 'Attachment'),
        ('card', 'Card'),
        ('carousel', 'Carousel'),
        ('typing', 'Typing'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Conversation'
    )
    
    sender_type = models.CharField(
        max_length=10,
        choices=SENDER_TYPES,
        verbose_name='Sender Type'
    )
    
    message_type = models.CharField(
        max_length=15,
        choices=MESSAGE_TYPES,
        default='text',
        verbose_name='Message Type'
    )
    
    content = models.TextField(
        validators=[MinLengthValidator(1)],
        verbose_name='Content'
    )
    
    response_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Response Data',
        help_text='Structured options or response details'
    )
    
    ai_confidence = models.FloatField(
        null=True,
        blank=True,
        verbose_name='AI Confidence',
        help_text='Confidence score of AI response (0.0 to 1.0)'
    )
    
    processing_time = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Processing Time',
        help_text='Processing time in seconds'
    )
    
    is_sensitive = models.BooleanField(
        default=False,
        verbose_name='Is Sensitive',
        help_text='Does the message contain sensitive info?'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Created At'
    )
    
    edited_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Edited At'
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadata'
    )
    
    class Meta:
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['sender_type', 'created_at']),
            models.Index(fields=['message_type']),
            models.Index(fields=['is_sensitive']),
        ]
    
    def __str__(self):
        content_preview = self.content[:50] + '...' if len(self.content) > 50 else self.content
        return f"{self.sender_type}: {content_preview}"
    
    @property
    def is_from_user(self):
        return self.sender_type == 'user'
    
    @property
    def is_from_bot(self):
        return self.sender_type == 'bot'
    
    # ============================================================================
    # ASYNC METHODS (Django 6.0 native async ORM)
    # ============================================================================
    
    @classmethod
    async def aget_by_conversation(cls, conversation_id, limit: int = 10):
        """Get messages by conversation ID (async)."""
        queryset = cls.objects.filter(conversation_id=conversation_id).select_related('conversation')
        return [m async for m in queryset.order_by('-created_at')[:limit]]
    
    @classmethod
    async def aget_recent_messages(cls, user, limit: int = 10):
        """Get recent messages for a user across all conversations (async)."""
        queryset = cls.objects.filter(
            conversation__session__user=user
        ).select_related('conversation', 'conversation__session')
        return [m async for m in queryset.order_by('-created_at')[:limit]]
    
    @classmethod
    async def aget_by_id(cls, message_id):
        """Get message by ID (async)."""
        try:
            return await cls.objects.select_related('conversation').aget(id=message_id)
        except cls.DoesNotExist:
            return None


class ChatbotResponse(models.Model):
    """
    Predefined responses mapped to categories.
    """
    
    RESPONSE_CATEGORIES = [
        ('greeting', 'Greeting'),
        ('sizing_inquiry', 'Sizing Inquiry'),
        ('styling_recommendation', 'Styling Recommendation'),
        ('order_help', 'Order Help'),
        ('shipping_returns', 'Shipping & Returns'),
        ('product_info', 'Product Info'),
        ('farewell', 'Farewell'),
        ('error', 'Error'),
        ('unknown', 'Unknown'),
    ]
    
    TARGET_USERS = [
        ('client', 'Client'),
        ('vendor', 'Vendor'),
        ('both', 'Both'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    category = models.CharField(
        max_length=25,
        choices=RESPONSE_CATEGORIES,
        verbose_name='Category'
    )
    
    target_user = models.CharField(
        max_length=10,
        choices=TARGET_USERS,
        default='both',
        verbose_name='Target User'
    )
    
    trigger_keywords = models.JSONField(
        default=list,
        verbose_name='Trigger Keywords'
    )
    
    response_text = models.TextField(
        verbose_name='Response Text'
    )
    
    response_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Response Data'
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name='Is Active'
    )
    
    priority = models.IntegerField(
        default=1,
        verbose_name='Priority',
        help_text='Higher number = higher priority'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Created At'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Updated At'
    )
    
    class Meta:
        verbose_name = 'Chatbot Response'
        verbose_name_plural = 'Chatbot Responses'
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['target_user', 'is_active']),
            models.Index(fields=['priority']),
        ]
    
    def __str__(self):
        return f"{self.category} - {self.target_user} (Priority: {self.priority})"
    
    # ============================================================================
    # ASYNC METHODS (Django 6.0 native async ORM)
    # ============================================================================
    
    @classmethod
    async def aget_by_category(cls, category: str, target_user: str = 'both'):
        """Get active responses by category (async)."""
        queryset = cls.objects.filter(
            category=category,
            target_user=target_user,
            is_active=True
        ).order_by('-priority', '-created_at')
        return [r async for r in queryset]
    
    @classmethod
    async def aget_active_responses(cls, target_user: str = 'both'):
        """Get all active responses for a target user (async)."""
        queryset = cls.objects.filter(
            target_user=target_user,
            is_active=True
        ).order_by('-priority', '-created_at')
        return [r async for r in queryset]
    
    @classmethod
    async def aget_by_id(cls, response_id):
        """Get response by ID (async)."""
        try:
            return await cls.objects.aget(id=response_id)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    async def aget_by_keywords(cls, keyword: str, target_user: str = 'both'):
        """Get responses matching a keyword (async)."""
        queryset = cls.objects.filter(
            trigger_keywords__icontains=keyword,
            target_user=target_user,
            is_active=True
        ).order_by('-priority', '-created_at')
        return [r async for r in queryset]