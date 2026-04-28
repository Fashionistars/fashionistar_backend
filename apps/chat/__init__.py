"""
apps/chat — FASHIONISTAR real-time buyer-vendor messaging domain.

Provides:
  • Conversation (buyer ↔ vendor thread, 1-to-many-products)
  • Message (text, image, system)
  • MessageMedia (Cloudinary direct-upload images)
  • ChatOffer (vendor ↦ buyer price proposals within a conversation)
  • ModerationFlag (abuse reports)
  • ChatEscalation (admin takeover of flagged threads)

Patterns:
  • All models extend TimeStampedModel for audit timestamps.
  • UUID PKs throughout.
  • Cloudinary two-phase direct-upload for MessageMedia.
  • conversation.atomic() for all state transitions.
  • Module-level imports for patchable test mocking.
"""
