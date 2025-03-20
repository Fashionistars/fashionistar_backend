from django.contrib import admin
from admin_backend.models import Brand
from import_export.admin import ImportExportModelAdmin
from django import forms


@admin.action(description="Mark selected brands as active")
def make_active(modeladmin, request, queryset):
    queryset.update(active=True)

@admin.action(description="Mark selected brands as inactive")
def make_inactive(modeladmin, request, queryset):
    queryset.update(active=False)


class BrandAdminForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = '__all__'

    def clean_title(self):
        title = self.cleaned_data['title']
        # Add custom validation here (e.g., check for unique brand names)
        return title


class ActiveBrandFilter(admin.SimpleListFilter):
    title = 'Active Brands'
    parameter_name = 'active_status'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active'),
            ('inactive', 'Inactive'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(active=True)
        if self.value() == 'inactive':
            return queryset.filter(active=False)


@admin.register(Brand)
class BrandAdmin(ImportExportModelAdmin):
    form = BrandAdminForm
    list_display = ['title', 'brand_image', 'active', 'created_at', 'updated_at', 'slug']
    list_editable = ['active']
    search_fields = ['title', 'slug']   # Enable search
    prepopulated_fields = {"slug": ("title",)}
    list_filter = [ActiveBrandFilter, 'created_at', 'updated_at']    # Add filters for active status and creation date
    actions = [make_active, make_inactive]


    # Expandable Admin Settings
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'image', 'slug', 'description')
        }),
        ('Status', {
            'fields': ('active',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),      # Collapse the timestamps section by default
        }),
    )

    readonly_fields = ('brand_image', 'created_at', 'updated_at')    