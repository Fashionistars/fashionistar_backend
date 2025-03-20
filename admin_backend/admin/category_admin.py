from django.contrib import admin
from admin_backend.models import Category
from store.models import Product  # Import Product model
from import_export.admin import ImportExportModelAdmin
from django import forms


# class ProductInline(admin.TabularInline):
#     model = Product
#     extra = 0  # Number of empty product forms to display
#     verbose_name = "Product"
#     verbose_name_plural = "Products in Category"
#     # Customize fields displayed in inline form
#     fields = ('title', 'price', 'status', 'featured')
#     readonly_fields = ('product_image',)
#     show_change_link = True

#     # Enable search and filters in inline list
#     search_fields = ['title', 'price']
#     list_filter = ['status', 'featured']


@admin.action(description="Mark selected categories as active")
def make_active(modeladmin, request, queryset):
    queryset.update(active=True)

@admin.action(description="Mark selected categories as inactive")
def make_inactive(modeladmin, request, queryset):
    queryset.update(active=False)


class CategoryAdminForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = '__all__'

    def clean_name(self):
        name = self.cleaned_data['name']
        # Add custom validation here (e.g., example: check for profanity)
        return name


class ActiveCategoryFilter(admin.SimpleListFilter):
    title = 'Active Categories'
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


@admin.register(Category)
class CategoryAdmin(ImportExportModelAdmin):
    form = CategoryAdminForm
    list_display = ['name', 'category_image', 'active', 'created_at', 'updated_at', 'slug']
    list_editable = ['active']
    search_fields = ['name', 'slug']          # Enable search
    prepopulated_fields = {"slug": ("name",)}
    list_filter = [ActiveCategoryFilter, 'created_at', 'updated_at']   # Add filters for active status and creation date
    actions = [make_active, make_inactive]
    # inlines = [ProductInline]  # Add the inline

    #Expandable Admin Settings
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'image', 'slug')
        }),
        ('Status', {
            'fields': ('active',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),          # Collapse the timestamps section by default
        }),
    )
    readonly_fields = ('category_image', 'created_at', 'updated_at')