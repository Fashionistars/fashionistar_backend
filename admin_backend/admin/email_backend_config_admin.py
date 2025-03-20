# admin_backend/admin/email_backend_config_admin.py
from django.contrib import admin

from django.contrib import messages  # Import messages framework
from django.shortcuts import redirect # Import redirect
from django import forms  # Import forms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _  # For internationalization

from admin_backend.models import EmailBackendConfig

from django.conf import settings
import logging

application_logger = logging.getLogger('application')

class EmailBackendConfigAdminForm(forms.ModelForm):
    class Meta:
        model = EmailBackendConfig
        fields = '__all__'  # Or specify the fields you want


@admin.register(EmailBackendConfig)
class EmailBackendConfigAdmin(admin.ModelAdmin):
    form = EmailBackendConfigAdminForm
    list_display = ['email_backend', 'created_at', 'updated_at']  # Display updated_at
    readonly_fields = ('created_at', 'updated_at')  # Make them read-only
    


    def has_add_permission(self, request):
        # Only allow adding if no instance exists
        return not EmailBackendConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Disallow deletion from the Admin View.
        return False
    
    

    fieldsets = (
        ('Email Configuration', {
            'fields': ('email_backend',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),  # Collapse the timestamps section by default
        }),
    )

