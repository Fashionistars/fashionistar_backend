from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password
from .models import UnifiedUser, BiometricCredential
from apps.common.models import DeletedRecords
from auditlog.models import LogEntry
import logging

logger = logging.getLogger('application')

# --- FORMS ---
class UnifiedUserChangeForm(forms.ModelForm):
    """Form for existing user updates."""
    class Meta:
        model = UnifiedUser
        fields = '__all__'

    def clean_password(self):
        # Regardless of what the user types, we don't save cleartext
        # Logic handled in save_model
        return self.cleaned_data.get("password")

class UnifiedUserCreationForm(forms.ModelForm):
    """Form for creating new users."""
    class Meta:
        model = UnifiedUser
        fields = ('email', 'phone', 'password', 'role')

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        phone = cleaned_data.get("phone")
        
        if not email and not phone:
            raise ValidationError("Either Email or Phone is required.")
        return cleaned_data

# --- INLINES ---
class BiometricInline(admin.TabularInline):
    model = BiometricCredential
    extra = 0
    readonly_fields = ('credential_id', 'sign_count', 'created_at')
    can_delete = True

# --- ADMIN CLASS ---
@admin.register(UnifiedUser)
class UnifiedUserAdmin(BaseUserAdmin):
    form = UnifiedUserChangeForm
    add_form = UnifiedUserCreationForm
    
    inlines = [BiometricInline]

    fieldsets = (
        (None, {'fields': ('email', 'phone', 'password')}),
        (_('Identity & Role'), {'fields': ('role', 'auth_provider', 'is_verified', 'pid')}),
        (_('Personal Info'), {'fields': ('first_name', 'last_name', 'avatar', 'bio')}),
        (_('Location'), {'fields': ('country', 'state', 'city', 'address')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Audit & Retention'), {'fields': ('last_login', 'date_joined', 'created_at', 'updated_at', 'is_deleted', 'deleted_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'phone', 'password', 'role', 'auth_provider'),
        }),
    )

    list_display = ('identifying_info', 'role', 'auth_provider', 'is_verified', 'is_active', 'is_deleted', 'created_at')
    list_filter = ('role', 'auth_provider', 'is_verified', 'is_active', 'is_deleted', 'country')
    search_fields = ('email', 'phone', 'first_name', 'last_name', 'pid')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at', 'deleted_at', 'last_login', 'date_joined')

    def identifying_info(self, obj):
        return obj.email if obj.email else str(obj.phone)
    identifying_info.short_description = "User Identifier"

    # --- SAVE LOGIC ---
    def save_model(self, request, obj, form, change):
        """
        Secure save: Handles password hashing and logging.
        """
        try:
            if not change: # Creating new
                obj.password = make_password(form.cleaned_data.get('password'))
            else:
                # Updating existing
                pass_input = form.cleaned_data.get('password')
                # Check if it's a new raw password or the existing hash
                if pass_input and not pass_input.startswith('pbkdf2_'): 
                    obj.password = make_password(pass_input)
            
            super().save_model(request, obj, form, change)
            logger.info(f"👮 Admin {request.user.email} saved User {obj.pk}")
            
        except Exception as e:
            logger.error(f"❌ Admin Save Error: {e}")

    def get_queryset(self, request):
        """Include soft-deleted users."""
        return UnifiedUser.objects.all_with_deleted() if hasattr(UnifiedUser.objects, 'all_with_deleted') else UnifiedUser.objects.all()

# --- AUDIT LOG ADMIN ---
# To view the history tracked by django-auditlog
from auditlog.admin import LogEntryAdmin
admin.site.unregister(LogEntry)
@admin.register(LogEntry)
class CustomLogEntryAdmin(LogEntryAdmin):
    list_display = ['created', 'resource_url', 'action', 'msg_short', 'user_url']
    search_fields = ['timestamp', 'object_repr', 'changes', 'actor__first_name', 'actor__last_name', 'actor__email']
    date_hierarchy = 'timestamp'
