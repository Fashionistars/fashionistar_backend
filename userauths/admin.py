from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from userauths.models import User, Profile
from django.utils import timezone
import datetime
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.hashers import make_password # Import make_password




import logging
# Get logger for application
application_logger = logging.getLogger('application')











from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from userauths.models import User, Profile
import logging

# Setup application logger
application_logger = logging.getLogger('application')


# 🚀 Custom User Form for Admin
class UserAdminForm(forms.ModelForm):
    email = forms.EmailField(required=False, help_text="Enter email or leave empty if using phone.")
    phone = forms.CharField(required=False, help_text="Enter phone or leave empty if using email.")
    password = forms.CharField(
        widget=forms.PasswordInput(),
        required=False,
        help_text="Leave blank to keep the current password."
    )
    role = forms.ChoiceField(choices=User.STATUS_CHOICES, required=True, help_text="Select the user role.")

    class Meta:
        model = User
        fields = ['email', 'phone', 'password', 'first_name', 'last_name', 'role', 'status', 'verified', 'is_active']

    def __init__(self, *args, **kwargs):
        """Ensure email, phone, and role are always included and preserved when updating an existing user."""
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            # 🔹 Ensure role, email, and phone fields are always included
            self.fields['role'] = forms.ChoiceField(choices=User.STATUS_CHOICES, required=False)
            self.fields['role'].initial = self.instance.role
            self.fields['role'].widget.attrs['readonly'] = True  # Prevent editing
            self.fields['role'].help_text = "Role cannot be changed after user creation."

            self.fields['email'] = forms.EmailField(required=False, initial=self.instance.email)
            self.fields['phone'] = forms.CharField(required=False, initial=self.instance.phone)

            self.fields['password'].required = False  # Password not required on updates

    def clean_role(self):
        """Preserve role when updating an existing user."""
        if self.instance and self.instance.pk:
            return self.instance.role  # Keep the existing role
        return self.cleaned_data.get('role')

    def clean_email(self):
        """Ensure email is preserved when updating an existing user."""
        email = self.cleaned_data.get('email')
        if self.instance.pk and not email:
            return self.instance.email  # Keep existing email
        return email

    def clean_phone(self):
        """Ensure phone is preserved when updating an existing user."""
        phone = self.cleaned_data.get('phone')
        if self.instance.pk and not phone:
            return self.instance.phone  # Keep existing phone
        return phone

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        phone = cleaned_data.get("phone")
        password = cleaned_data.get("password")

        # Ensure either email or phone is provided
        if not email and not phone:
            raise ValidationError("Either an email or a phone number must be provided.")

        # Ensure password is required only for new users
        if not self.instance.pk and not password:
            raise ValidationError({'password': 'Password is required when creating a new user.'})

        return cleaned_data


# 🚀 Custom User Admin
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    search_fields = ['email', 'phone', 'first_name', 'last_name']
    list_display = ['identifying_info', 'role', 'is_active', 'verified']
    readonly_fields = ['date_joined', 'last_login']

    fieldsets = (
        (_('User Information'), {'fields': ('email', 'phone', 'role', 'password', 'first_name', 'last_name')}),
        (_('Permissions'), {'fields': ('is_active', 'verified', 'is_staff', 'is_superuser')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )

    def get_readonly_fields(self, request, obj=None):
        """Prevent editing of email, phone, and role after creation."""
        if obj:
            return ['email', 'phone', 'role'] + self.readonly_fields
        return self.readonly_fields

    def identifying_info(self, obj):
        return obj.email if obj.email else obj.phone
    identifying_info.short_description = _('User')

    def save_model(self, request, obj, form, change):
        """Ensure passwords are hashed, existing passwords are preserved, and log admin actions."""
        if form.cleaned_data.get('password'):
            obj.password = make_password(form.cleaned_data['password'])
        else:
            # Preserve existing password if none is provided
            obj.password = User.objects.get(pk=obj.pk).password

        application_logger.info(f"User {obj.identifying_info} updated by {request.user} on {timezone.now()}")

        super().save_model(request, obj, form, change)


# 🚀 Custom Profile Admin
class ProfileAdmin(admin.ModelAdmin):
    search_fields = ['user__email', 'user__phone', 'full_name']
    list_display = ['thumbnail', 'user', 'full_name', 'country', 'state', 'city']
    readonly_fields = ['pid']

    def thumbnail(self, obj):
        """Display profile image preview."""
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" width="50" height="50" style="border-radius: 50%; object-fit: cover;" />')
        return "No Image"
    thumbnail.short_description = "Profile Image"

# ✅ Register models with admin panel
admin.site.register(User, UserAdmin)
admin.site.register(Profile, ProfileAdmin)






































