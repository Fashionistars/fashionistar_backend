# apps/support/serializers/support_serializers.py
"""
Support domain serializers.

Architecture:
  - Read serializers (SupportTicketSerializer, TicketMessageSerializer):
    Full nested representation for GET responses.
  - Write serializers (SupportTicketWriteSerializer, TicketMessageWriteSerializer):
    Client-facing fields only — validated, no nested write.
  - Staff-only serializers (TicketStatusUpdateSerializer, TicketEscalationSerializer).
"""

from rest_framework import serializers

from apps.support.models import (
    SupportTicket,
    TicketMessage,
    TicketEscalation,
    TicketStatus,
    TicketPriority,
    TicketCategory,
)


# ─────────────────────────────────────────────────────────────────────────────
# TICKET MESSAGE
# ─────────────────────────────────────────────────────────────────────────────

class TicketMessageSerializer(serializers.ModelSerializer):
    """Read serializer for a threaded support message."""
    author_name = serializers.SerializerMethodField()

    class Meta:
        model  = TicketMessage
        fields = [
            "id",
            "author_name",
            "body",
            "is_staff_reply",
            "attachments",
            "created_at",
        ]

    def get_author_name(self, obj: TicketMessage) -> str:
        if obj.author:
            return obj.author.get_full_name() or obj.author.email
        return "Deleted User"


class TicketMessageWriteSerializer(serializers.Serializer):
    """
    Write serializer for adding a message to a ticket thread.
    Used by both client and staff — is_staff is resolved server-side.
    """
    body        = serializers.CharField(min_length=2, max_length=5000)
    attachments = serializers.ListField(
        child=serializers.CharField(max_length=500),
        max_length=5,
        default=list,
        required=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TICKET ESCALATION
# ─────────────────────────────────────────────────────────────────────────────

class TicketEscalationSerializer(serializers.ModelSerializer):
    """Read serializer for a ticket escalation record."""

    class Meta:
        model  = TicketEscalation
        fields = [
            "id",
            "status",
            "reason",
            "resolution_notes",
            "resolved_at",
            "created_at",
        ]


# ─────────────────────────────────────────────────────────────────────────────
# SUPPORT TICKET (READ)
# ─────────────────────────────────────────────────────────────────────────────

class SupportTicketSerializer(serializers.ModelSerializer):
    """
    Full read serializer for a SupportTicket.
    Includes nested message thread and escalation record.
    """
    messages   = TicketMessageSerializer(many=True, read_only=True)
    escalation = TicketEscalationSerializer(read_only=True)
    submitter_email = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()

    class Meta:
        model  = SupportTicket
        fields = [
            "id",
            "submitter_email",
            "assigned_to_name",
            "order_id",
            "category",
            "priority",
            "status",
            "title",
            "description",
            "metadata",
            "resolution_notes",
            "resolved_at",
            "closed_at",
            "messages",
            "escalation",
            "created_at",
            "updated_at",
        ]

    def get_submitter_email(self, obj: SupportTicket) -> str | None:
        return obj.submitter.email if obj.submitter else None

    def get_assigned_to_name(self, obj: SupportTicket) -> str | None:
        if obj.assigned_to:
            return obj.assigned_to.get_full_name() or obj.assigned_to.email
        return None


class SupportTicketListSerializer(serializers.ModelSerializer):
    """Lightweight list serializer — no nested thread (performance)."""
    submitter_email = serializers.SerializerMethodField()

    class Meta:
        model  = SupportTicket
        fields = [
            "id",
            "submitter_email",
            "category",
            "priority",
            "status",
            "title",
            "order_id",
            "created_at",
            "updated_at",
        ]

    def get_submitter_email(self, obj: SupportTicket) -> str | None:
        return obj.submitter.email if obj.submitter else None


# ─────────────────────────────────────────────────────────────────────────────
# SUPPORT TICKET (WRITE)
# ─────────────────────────────────────────────────────────────────────────────

class SupportTicketWriteSerializer(serializers.Serializer):
    """
    Create serializer for a new support ticket.
    Client-facing fields only — submitter resolved from request.user.
    """
    title       = serializers.CharField(min_length=5, max_length=300)
    description = serializers.CharField(min_length=10, max_length=5000)
    category    = serializers.ChoiceField(
        choices=TicketCategory.choices,
        default=TicketCategory.GENERAL,
    )
    priority    = serializers.ChoiceField(
        choices=TicketPriority.choices,
        default=TicketPriority.MEDIUM,
        required=False,
    )
    order_id    = serializers.UUIDField(required=False, allow_null=True)
    metadata    = serializers.DictField(required=False, default=dict)


# ─────────────────────────────────────────────────────────────────────────────
# STATUS UPDATE (Staff only)
# ─────────────────────────────────────────────────────────────────────────────

class TicketStatusUpdateSerializer(serializers.Serializer):
    """
    Staff-only serializer for status transitions.
    Validates the target status and optional resolution notes.
    """
    status = serializers.ChoiceField(choices=TicketStatus.choices)
    notes  = serializers.CharField(
        max_length=5000,
        required=False,
        allow_blank=True,
        default="",
    )


class TicketEscalateSerializer(serializers.Serializer):
    """Staff-only serializer for escalating a ticket."""
    reason = serializers.CharField(min_length=10, max_length=2000)
