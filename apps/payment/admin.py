from django.contrib import admin

from apps.payment.models import PaymentIntent, PaymentProvider, PaymentProviderLog, PaymentWebhookEvent, PaystackTransferRecipient


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = ("reference", "user", "purpose", "amount", "currency", "status", "provider", "created_at")
    list_filter = ("provider", "purpose", "status", "currency")
    search_fields = ("reference", "provider_reference", "user__email", "order_id")
    readonly_fields = ("provider_response", "created_at", "updated_at")


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event", "reference", "processed", "created_at")
    list_filter = ("provider", "event", "processed")
    search_fields = ("reference", "event_id", "payload_hash")
    readonly_fields = ("payload", "processing_error", "created_at", "updated_at")


admin.site.register(PaymentProvider)
admin.site.register(PaystackTransferRecipient)
admin.site.register(PaymentProviderLog)
