# apps/authentication/admin.py
"""
Enterprise-Grade Admin Configuration — UnifiedUser & BiometricCredential.

Architecture:
    - UnifiedUserCreationForm:  Strict validation for NEW user creation.
    - UnifiedUserChangeForm:    Immutability guards for EXISTING users.
    - UnifiedUserAdmin:         Full-featured admin with import/export,
                                 avatar thumbnails, soft-delete actions,
                                 and structured audit logging.
    - BiometricInline:          Inline editor for WebAuthn credentials.
    - CustomLogEntryAdmin:      Enhanced audit-log viewer.

Mirrors the validated legacy ``userauths/admin.py`` pattern,
adapted for the upgraded ``UnifiedUser`` model, Django 6.0.2,
and the enterprise dependency stack (django-import-export,
django-auditlog, django-jazzmin).
"""

import logging

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from auditlog.admin import LogEntryAdmin
from auditlog.models import LogEntry

from apps.common.admin_mixins import SoftDeleteAdminMixin

from apps.authentication.models import UnifiedUser, BiometricCredential

logger = logging.getLogger('application')


# ================================================================
# 1. IMPORT / EXPORT RESOURCE
# ================================================================

class UnifiedUserResource(resources.ModelResource):
    """
    django-import-export resource for bulk CSV/XLSX
    import and export of UnifiedUser records.

    Excludes sensitive fields (password, permissions) from
    export to prevent accidental data leakage.
    """

    class Meta:
        model = UnifiedUser
        fields = (
            'id',
            'email',
            'phone',
            'first_name',
            'last_name',
            'role',
            'auth_provider',
            'is_verified',
            'is_active',
            'is_deleted',
            'country',
            'state',
            'city',
            'date_joined',
            'last_login',
            'created_at',
            'updated_at',
        )
        export_order = fields


# ================================================================
# 2. FORMS — Creation & Change
# ================================================================

class UnifiedUserCreationForm(forms.ModelForm):
    """
    Admin form for creating NEW UnifiedUser records.

    Enforces:
        - Email / Phone mutual-exclusivity (at least one required).
        - Password is mandatory for new users.
        - Role must be a valid choice from ``ROLE_CHOICES``.

    Mirrors the legacy ``UserAdminForm`` validation pattern.
    """

    email = forms.EmailField(
        required=False,
        help_text=_(
            "Enter email or leave empty if using phone."
        ),
    )
    phone = forms.CharField(
        required=False,
        help_text=_(
            "Enter phone or leave empty if using email."
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(),
        required=True,
        help_text=_(
            "Password is required when creating a new user."
        ),
    )
    role = forms.ChoiceField(
        choices=UnifiedUser.ROLE_CHOICES,
        required=True,
        help_text=_("Select the user role."),
    )

    class Meta:
        model = UnifiedUser
        fields = (
            'email',
            'phone',
            'password',
            'role',
            'auth_provider',
            'first_name',
            'last_name',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Disable field-level required so clean() handles
        # all validation with human-readable messages
        self.fields['password'].required = False
        self.fields['role'].required = False

    def clean_first_name(self):
        from django.utils.html import strip_tags
        value = self.cleaned_data.get('first_name', '')
        return strip_tags(value).strip()

    def clean_last_name(self):
        from django.utils.html import strip_tags
        value = self.cleaned_data.get('last_name', '')
        return strip_tags(value).strip()

    def clean(self):
        """
        Cross-field validation for new user creation.

        Raises:
            ValidationError: If neither email nor phone is
                provided.
        """
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        phone = cleaned_data.get('phone')
        password = cleaned_data.get('password')
        role = cleaned_data.get('role')
        auth_provider = cleaned_data.get('auth_provider')
        errors = {}

        # 1. Identifier required
        if not email and not phone:
            errors['email'] = _(
                "Either an email or a phone number "
                "must be provided."
            )

        # 2. Password required
        if not password:
            errors['password'] = _(
                "Password is required when creating "
                "a new user."
            )

        # 3. Role required
        if not role:
            errors['role'] = _(
                "Please select a role for the new user."
            )

        # 4. Auth_provider ↔ identifier cross-validation
        if auth_provider == 'email' and not email:
            errors['auth_provider'] = _(
                'Auth provider "email" requires an '
                'email address.'
            )
        elif auth_provider == 'phone' and not phone:
            errors['auth_provider'] = _(
                'Auth provider "phone" requires a '
                'phone number.'
            )
        elif auth_provider == 'email' and email and phone:
            errors['phone'] = _(
                'Email auth provider should not have '
                'a phone number.'
            )
        elif auth_provider == 'phone' and phone and email:
            errors['email'] = _(
                'Phone auth provider should not have '
                'an email address.'
            )

        if errors:
            raise ValidationError(errors)

        return cleaned_data


class UnifiedUserChangeForm(forms.ModelForm):
    """
    Admin form for updating EXISTING UnifiedUser records.

    Immutability guards:
        - ``email``, ``phone``, ``role``, ``auth_provider``
          are preserved from the database and cannot be
          changed via the admin form after creation.
        - Password field is optional; hashing is handled
          in ``save_model()``, not in the form.

    Mirrors the legacy ``UserAdminForm.__init__`` / ``clean_*``
    pattern for field locking.
    """

    email = forms.EmailField(
        required=False,
        help_text=_(
            "Email cannot be changed after user creation."
        ),
    )
    phone = forms.CharField(
        required=False,
        help_text=_(
            "Phone cannot be changed after user creation."
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(),
        required=False,
        help_text=_(
            "Leave blank to keep the current password."
        ),
    )
    role = forms.ChoiceField(
        choices=UnifiedUser.ROLE_CHOICES,
        required=False,
        help_text=_(
            "Role cannot be changed after user creation."
        ),
    )

    class Meta:
        model = UnifiedUser
        exclude = ('password',)

    def __init__(self, *args, **kwargs):
        """
        Lock immutable fields for existing users.

        Sets ``readonly`` widget attribute and populates
        initial values from the database instance to prevent
        accidental modification.
        """
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            # Lock immutable identity fields
            for field_name in ('email', 'phone', 'role',
                               'auth_provider'):
                if field_name in self.fields:
                    self.fields[field_name].widget.attrs[
                        'readonly'
                    ] = True

    # -- Per-field immutability guards --

    def clean_email(self):
        """
        Preserve email on existing users.

        Returns:
            str or None: The original email from the database
                if the user already exists, otherwise the
                submitted value.
        """
        if self.instance and self.instance.pk:
            return self.instance.email
        return self.cleaned_data.get('email')

    def clean_phone(self):
        """
        Preserve phone on existing users.

        Returns:
            str or None: The original phone from the database
                if the user already exists, otherwise the
                submitted value.
        """
        if self.instance and self.instance.pk:
            return self.instance.phone
        return self.cleaned_data.get('phone')

    def clean_role(self):
        """
        Preserve role on existing users.

        Returns:
            str: The original role from the database if the
                user already exists, otherwise the submitted
                value.
        """
        if self.instance and self.instance.pk:
            return self.instance.role
        return self.cleaned_data.get('role')

    def clean_auth_provider(self):
        """
        Preserve auth_provider on existing users.

        Returns:
            str: The original auth_provider from the database
                if the user already exists, otherwise the
                submitted value.
        """
        if self.instance and self.instance.pk:
            return self.instance.auth_provider
        return self.cleaned_data.get('auth_provider')

    def clean_password(self):
        """
        Pass-through for password field.

        Hashing is handled in ``UnifiedUserAdmin.save_model()``,
        not in the form clean step, to keep separation of
        concerns.

        Returns:
            str: The raw password input (or empty string).
        """
        return self.cleaned_data.get('password')

    def clean(self):
        """
        Cross-field validation for existing users.

        Ensures the user still has at least one identifier
        (email or phone) — guards against accidental removal.

        Raises:
            ValidationError: If both email and phone are empty.
        """
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        phone = cleaned_data.get('phone')

        if not email and not phone:
            raise ValidationError(
                _("Either an email or a phone number "
                  "must be provided.")
            )

        return cleaned_data


# ================================================================
# 3. INLINES
# ================================================================

class BiometricInline(admin.TabularInline):
    """
    Inline editor for FIDO2/WebAuthn biometric credentials.

    Displays credential metadata in a compact table within
    the UnifiedUser change form. Sensitive fields
    (``credential_id``, ``sign_count``, ``created_at``) are
    read-only.
    """

    model = BiometricCredential
    extra = 0
    readonly_fields = (
        'credential_id',
        'sign_count',
        'created_at',
    )
    can_delete = True


# ================================================================
# 4. ADMIN CLASS — UnifiedUserAdmin
# ================================================================

@admin.register(UnifiedUser)
class UnifiedUserAdmin(
    SoftDeleteAdminMixin,
    ImportExportModelAdmin,
    BaseUserAdmin,
):
    """
    Enterprise-grade admin for the UnifiedUser model.

    Features:
        - Dual forms: ``UnifiedUserCreationForm`` (add) and
          ``UnifiedUserChangeForm`` (edit) with immutability
          guards.
        - Import/Export via ``django-import-export`` for bulk
          CSV/XLSX operations.
        - Avatar thumbnail preview in ``list_display``.
        - Soft-delete and restore bulk actions.
        - Structured ``try/except`` in ``save_model`` with
          lazy ``%s`` audit logging.
        - ``get_readonly_fields`` locks identity fields on
          existing users (mirrors legacy pattern).
        - ``date_hierarchy`` on ``date_joined`` for quick
          temporal filtering.

    Fieldset layout mirrors the legacy admin UI:
        Tab 1 — User Information (email, phone, role, etc.)
        Tab 2 — Permissions (is_active, is_verified, staff, etc.)
        Tab 3 — Important Dates (last_login, date_joined, etc.)
        Tab 4 — Personal Info (first_name, last_name, bio, etc.)
        Tab 5 — Location (country, state, city, address)
        Tab 6 — Audit & Retention (timestamps, soft-delete)
    """

    # -- Forms --
    form = UnifiedUserChangeForm
    add_form = UnifiedUserCreationForm
    resource_class = UnifiedUserResource

    # -- Inlines --
    # -- Inlines --
    inlines = [BiometricInline]

    def get_inlines(self, request, obj=None):
        """Hide biometric inline when creating a new user."""
        if obj is None:
            return []
        return super().get_inlines(request, obj)

    # -- Performance (1M+ users) --
    list_per_page = 25
    list_max_show_all = 100
    show_full_result_count = False  # Avoids COUNT(*) on large tables
    list_select_related = True

    # -- Fieldsets (Change form) --
    fieldsets = (
        (_('User Information'), {
            'fields': (
                'email',
                'phone',
                'role',
                'password',
                'auth_provider',
                'pid',
            ),
        }),
        (_('Personal Info'), {
            'fields': (
                'first_name',
                'last_name',
                'avatar',
                'bio',
            ),
        }),
        (_('Permissions'), {
            'fields': (
                'is_active',
                'is_verified',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions',
            ),
        }),
        (_('Important Dates'), {
            'fields': (
                'last_login',
                'date_joined',
            ),
        }),
        (_('Location'), {
            'fields': (
                'country',
                'state',
                'city',
                'address',
            ),
        }),
        (_('Audit & Retention'), {
            'fields': (
                'created_at',
                'updated_at',
                'is_deleted',
                'deleted_at',
            ),
            'classes': ('collapse',),
        }),
    )

    # -- Add fieldsets (Creation form) --
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email',
                'phone',
                'password',
                'first_name',
                'last_name',
                'role',
                'auth_provider',
            ),
        }),
    )

    # -- List view --
    list_display = (
        'avatar_thumbnail',
        'identifying_info',
        'role',
        'auth_provider',
        'is_verified',
        'is_active',
        'is_deleted',
        'last_login',
        'created_at',
    )
    list_filter = (
        'role',
        'auth_provider',
        'is_verified',
        'is_active',
        'is_deleted',
        'country',
    )
    search_fields = (
        'email',
        'phone',
        'first_name',
        'last_name',
        'pid',
    )
    ordering = ('-date_joined',)
    date_hierarchy = 'date_joined'

    # -- Read-only timestamps --
    readonly_fields = (
        'last_login',
        'date_joined',
        'created_at',
        'updated_at',
        'deleted_at',
    )

    # -- Bulk actions --
    actions = [
        'soft_delete_selected',
        'restore_selected',
    ]

    # ---- Display helpers ----

    def identifying_info(self, obj):
        """
        Return the primary user identifier for the list view.

        Delegates to the model's ``identifying_info`` property
        for consistency across admin, logging, and API layers.

        Args:
            obj: The UnifiedUser instance.

        Returns:
            str: Email, phone, or fallback string.
        """
        return obj.identifying_info

    identifying_info.short_description = _('User')
    identifying_info.admin_order_field = 'email'

    def avatar_thumbnail(self, obj):
        """
        Render a circular avatar preview in the list view.

        Mirrors the legacy ``ProfileAdmin.thumbnail()`` pattern.
        Falls back to a placeholder dash if no avatar is set.

        Args:
            obj: The UnifiedUser instance.

        Returns:
            str: Safe HTML ``<img>`` tag or placeholder.
        """
        if obj.avatar:
            return mark_safe(
                '<img src="%s" width="35" height="35" '
                'style="border-radius: 50%%; '
                'object-fit: cover;" />' % obj.avatar.url
            )
        return "-"

    avatar_thumbnail.short_description = _('Avatar')

    # ---- Field locking ----

    def get_readonly_fields(self, request, obj=None):
        """
        Lock identity fields on existing users.

        For NEW users (obj is None), only the auto-timestamp
        fields are read-only. For EXISTING users, email, phone,
        role, and auth_provider are also locked — mirroring
        the legacy ``UserAdmin.get_readonly_fields`` pattern
        and the model's ``clean()`` immutability guards.

        Args:
            request: The current HTTP request.
            obj: The UnifiedUser instance (None on creation).

        Returns:
            tuple: Read-only field names.
        """
        if obj:
            return (
                'email',
                'phone',
                'role',
                'auth_provider',
            ) + self.readonly_fields
        return self.readonly_fields

    # ---- Save logic ----

    def save_model(self, request, obj, form, change):
        """
        Secure save with password hashing and audit logging.

        On CREATE:
            - Hashes the raw password via ``make_password``.
        On UPDATE:
            - If a new raw password is submitted, hashes it.
            - If the password field is blank, preserves the
              existing hash from the database.
            - Identity fields are already guarded by the form's
              ``clean_*`` methods and ``get_readonly_fields``.

        All operations are wrapped in a structured try/except
        with lazy ``%s`` logging (PEP 8, cp1252-safe).

        Args:
            request: The current HTTP request.
            obj: The UnifiedUser instance being saved.
            form: The bound admin form.
            change: True if updating, False if creating.
        """
        try:
            if not change:
                # --- CREATE: hash the new password ---
                raw_password = form.cleaned_data.get('password')
                if raw_password:
                    obj.password = make_password(raw_password)

                logger.info(
                    "Admin %s creating new user [role=%s]",
                    request.user.pk,
                    obj.role,
                )
            else:
                # --- UPDATE: hash only if a new password
                # was submitted ---
                raw_password = form.cleaned_data.get('password')
                if raw_password and not raw_password.startswith(
                    ('pbkdf2_', 'bcrypt', 'argon2')
                ):
                    obj.password = make_password(raw_password)
                else:
                    # Preserve existing password hash.
                    # Must use all_with_deleted() because the
                    # default manager filters out soft-deleted
                    # users, which would crash with DoesNotExist
                    # when editing a soft-deleted record.
                    existing = UnifiedUser.objects.all_with_deleted().get(
                        pk=obj.pk,
                    )
                    obj.password = existing.password

                logger.info(
                    "Admin %s updated user %s at %s",
                    request.user.pk,
                    obj.pk,
                    timezone.now().isoformat(),
                )

            super().save_model(request, obj, form, change)

            logger.info(
                "Successfully saved UnifiedUser %s "
                "[provider=%s, role=%s]",
                obj.pk,
                obj.auth_provider,
                obj.role,
            )

        except Exception:
            logger.exception(
                "Admin save failed for UnifiedUser %s "
                "by admin %s",
                obj.pk,
                request.user.pk,
            )
            raise

    # ---- Soft-delete behavior ----
    # Inherited from SoftDeleteAdminMixin:
    #   - get_queryset()         -> includes soft-deleted records
    #   - delete_model()         -> soft-delete instead of hard-delete
    #   - soft_delete_selected() -> bulk soft-delete action
    #   - restore_selected()     -> bulk restore action


# ================================================================
# 5. AUDIT LOG ADMIN — django-auditlog
# ================================================================

# Unregister the default LogEntry admin so we can register
# our enhanced version with better search and display.
try:
    admin.site.unregister(LogEntry)
except admin.sites.NotRegistered:
    pass


@admin.register(LogEntry)
class CustomLogEntryAdmin(LogEntryAdmin):
    """
    Enhanced audit-log viewer for django-auditlog.

    Adds date hierarchy, expanded search, and a cleaner
    ``list_display`` for the admin dashboard.
    """

    list_display = [
        'created',
        'resource_url',
        'action',
        'msg_short',
        'user_url',
    ]
    search_fields = [
        'timestamp',
        'object_repr',
        'changes',
        'actor__first_name',
        'actor__last_name',
        'actor__email',
    ]
    date_hierarchy = 'timestamp'
