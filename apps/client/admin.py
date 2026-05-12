# apps/client/admin.py
"""
Client Domain Admin.
"""
from django.contrib import admin

from apps.client.models import ClientAddress, ClientProfile


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "country",
        "preferred_size",
        "total_orders",
        "total_spent_ngn",
        "is_profile_complete",
        "created_at",
    ]
    list_filter  = ["country", "preferred_size", "is_profile_complete"]
    search_fields = ["user__email", "user__phone"]
    readonly_fields = ["created_at", "updated_at", "total_orders", "total_spent_ngn"]
    ordering = ["-created_at"]


@admin.register(ClientAddress)
class ClientAddressAdmin(admin.ModelAdmin):
    list_display = [
        "client",
        "label",
        "city",
        "state",
        "country",
        "is_default",
    ]
    list_filter  = ["country", "is_default"]
    search_fields = ["client__user__email", "street_address", "city"]
    ordering = ["-created_at"]
