# apps/vendor/admin.py
"""Vendor Domain Admin."""
from django.contrib import admin

from apps.vendor.models import VendorPayoutProfile, VendorProfile, VendorSetupState


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display  = ["user", "store_name", "store_slug", "country", "is_verified", "is_active", "created_at"]
    list_filter   = ["is_verified", "is_active", "is_featured", "country"]
    search_fields = ["user__email", "store_name", "store_slug"]
    readonly_fields = ["created_at", "updated_at", "total_products", "total_sales", "total_revenue"]
    ordering = ["-created_at"]


@admin.register(VendorSetupState)
class VendorSetupStateAdmin(admin.ModelAdmin):
    list_display  = ["vendor", "current_step", "onboarding_done"]
    list_filter   = ["onboarding_done", "profile_complete"]
    search_fields = ["vendor__user__email", "vendor__store_name"]


@admin.register(VendorPayoutProfile)
class VendorPayoutProfileAdmin(admin.ModelAdmin):
    list_display  = ["vendor", "bank_name", "account_name", "account_last4", "is_verified"]
    list_filter   = ["is_verified", "bank_name"]
    search_fields = ["vendor__user__email", "account_name"]
    readonly_fields = ["account_number_enc", "account_last4"]
