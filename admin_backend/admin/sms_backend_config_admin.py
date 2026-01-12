from django.contrib import admin
from django import forms
from admin_backend.models.sms_backend_config import SMSBackendConfig

class SMSBackendConfigAdminForm(forms.ModelForm):
    class Meta:
        model = SMSBackendConfig
        fields = '__all__'

@admin.register(SMSBackendConfig)
class SMSBackendConfigAdmin(admin.ModelAdmin):
    form = SMSBackendConfigAdminForm
    list_display = ['sms_backend', 'created_at', 'updated_at']
    readonly_fields = ('created_at', 'updated_at')

    def has_add_permission(self, request):
        return not SMSBackendConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    fieldsets = (
        ('SMS Configuration', {
            'fields': ('sms_backend',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
