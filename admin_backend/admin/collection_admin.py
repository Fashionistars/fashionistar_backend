from django.contrib import admin
from admin_backend.models import Collections
from store.models import Product  # Import Product model
from import_export.admin import ImportExportModelAdmin
from django import forms






# class ProductInline(admin.TabularInline):
#     model = Product
#     extra = 0  # Number of empty product forms to display
#     verbose_name = "Product"
#     verbose_name_plural = "Products in Collection"
#     # Customize fields displayed in inline form
#     fields = ('title', 'price', 'status', 'featured')
#     readonly_fields = ('product_image',)
#     show_change_link = True

#     # Enable search and filters in inline list
#     search_fields = ['title', 'price']
#     list_filter = ['status', 'featured']




class CollectionsAdminForm(forms.ModelForm):
    class Meta:
        model = Collections
        fields = '__all__'




@admin.register(Collections)
class CollectionsAdmin(ImportExportModelAdmin):
    form = CollectionsAdminForm
    list_display = ['title', 'sub_title', 'slug', 'created_at', 'updated_at']
    search_fields = ['title', 'sub_title', 'description', 'slug']
    prepopulated_fields = {"slug": ("title",)}
    list_filter = ['created_at', 'updated_at']
    # inlines = [ProductInline]  # Add the inline

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'sub_title', 'description', 'slug'),
        }),
        ('Images', {
            'fields': ('background_image', 'image'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('created_at', 'updated_at')  # Date fields should not be editable


    